"""Meeting overview contracts against real Flask routes and isolated SQLite."""
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from flask_jwt_extended import create_access_token
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.ext.compiler import compiles
from exts import db
from models import CampMeeting, CampSession, CampMember
import test_training_groups as training_fixtures


@compiles(MEDIUMTEXT, 'sqlite')
def sqlite_mediumtext(_type, _compiler, **_kwargs):
    return 'TEXT'


class MeetingOverviewTest(unittest.TestCase):
    def setUp(self):
        self.fixture = training_fixtures.TrainingSmoke()
        self.fixture.setUp()
        # CampUnit's joined project mapping is an ORM dependency beyond its FKs.
        db.create_all()
        self.client, self.headers = self.fixture.client_as(self.fixture.actor)
        self.sid = self.fixture.camp.id
        self.owner_id = self.fixture.owner.id
        self.other_id = self.fixture.other.id
        for day, mentor, count in [
            ('2026-11-13', self.owner_id, 3),
            ('2026-11-12', self.other_id, 1),
            ('2026-11-10', self.owner_id, 1),
        ]:
            for index in range(count):
                db.session.add(CampMeeting(camp_session_id=self.sid, scope='team',
                    mentor_id=mentor, title=f'{day} meeting {index}',
                    meeting_date=date.fromisoformat(day), created_by=mentor))
        other_camp = CampSession(name='Other camp', category='learning', status='running',
                                 start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        db.session.add(other_camp)
        db.session.flush()
        db.session.add(CampMeeting(camp_session_id=other_camp.id, scope='team',
            mentor_id=self.fixture.student.id, title='Private meeting in other camp',
            meeting_date=date(2026, 11, 13), created_by=self.fixture.student.id))
        db.session.commit()

    def tearDown(self):
        self.fixture.doCleanups()
        self.fixture.tearDown()

    def get(self, **params):
        return self.client.get(f'/camp/sessions/{self.sid}/meetings/all',
                               query_string=params, headers=self.headers)

    def test_dates_are_complete_and_cursor_has_no_overlap(self):
        first = self.get(limit=1)
        self.assertEqual(first.status_code, 200, first.json)
        self.assertEqual(first.json['total'], 5)
        self.assertEqual(len(first.json['groups']), 1)
        self.assertEqual(first.json['groups'][0]['date'], '2026-11-13')
        self.assertEqual(len(first.json['groups'][0]['meetings']), 3)
        self.assertTrue(first.json['has_more'])
        self.assertEqual(first.json['next_before_date'], '2026-11-13')
        second = self.get(limit=2, before_date=first.json['next_before_date']).json
        self.assertEqual(second['total'], 5)
        self.assertEqual([g['date'] for g in second['groups']], ['2026-11-12', '2026-11-10'])
        self.assertFalse(second['has_more'])
        self.assertIsNone(second['next_before_date'])

    def test_mentor_lookup_stays_complete_after_filtering(self):
        result = self.get(limit=1, mentor_id=self.owner_id).json
        self.assertEqual(result['total'], 4)
        self.assertEqual({m['user_id'] for m in result['mentors']}, {self.owner_id, self.other_id})
        self.assertTrue(all(m['mentor_id'] == self.owner_id for g in result['groups'] for m in g['meetings']))

    def test_date_range_is_inclusive_and_combines_with_mentor(self):
        result = self.get(limit=10, start_date='2026-11-10', end_date='2026-11-12').json
        self.assertEqual(result['total'], 2)
        result = self.get(limit=10, mentor_id=self.owner_id,
                          start_date='2026-11-10', end_date='2026-11-12').json
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['groups'][0]['date'], '2026-11-10')

    def test_roster_marks_current_mentors_and_preserves_historical_records(self):
        db.session.add(CampMeeting(camp_session_id=self.sid, scope='team',
            mentor_id=self.fixture.student.id, title='Historical mentor meeting',
            meeting_date=date(2026, 11, 11), created_by=self.fixture.student.id))
        db.session.commit()
        result = self.get(limit=7, start_date='2026-11-09', end_date='2026-11-15').json
        roster = {row['user_id']: row['is_current'] for row in result['mentors']}
        self.assertTrue(roster[self.owner_id])
        self.assertTrue(roster[self.other_id])
        self.assertFalse(roster[self.fixture.student.id])
        self.assertFalse(result['has_more'])
        self.assertEqual(sum(len(group['meetings']) for group in result['groups']), 6)

    def test_current_roster_survives_empty_week_and_excludes_removed_member(self):
        member = CampMember.query.filter_by(camp_session_id=self.sid, user_id=self.other_id).one()
        member.status = 'removed'
        db.session.commit()
        result = self.get(limit=7, start_date='2026-12-07', end_date='2026-12-13').json
        self.assertEqual(result['groups'], [])
        roster = {row['user_id']: row['is_current'] for row in result['mentors']}
        self.assertTrue(roster[self.owner_id])
        self.assertFalse(roster[self.other_id])

    def test_invalid_cursor_dates_and_limits_are_rejected(self):
        for params in [{'limit': 0}, {'limit': 51}, {'limit': 'x'},
                       {'limit': 1, 'before_date': '2026-02-30'},
                       {'limit': 1, 'start_date': '2026-1-2'},
                       {'limit': 1, 'end_date': 'bad'},
                       {'limit': 1, 'start_date': '2026-11-13', 'end_date': '2026-11-12'}]:
            with self.subTest(params=params):
                self.assertEqual(self.get(**params).status_code, 400)

    def test_old_page_clients_keep_their_contract(self):
        result = self.get(page=2, page_size=2).json
        self.assertEqual(result['page'], 2)
        self.assertEqual(result['page_size'], 2)
        self.assertEqual(result['total'], 5)
        self.assertEqual(len(result['meetings']), 2)

    def test_empty_results_and_unauthorized_or_foreign_mentor(self):
        result = self.get(limit=10, start_date='2026-12-01').json
        self.assertEqual(result['groups'], [])
        self.assertEqual(result['total'], 0)
        self.assertFalse(result['has_more'])
        self.assertEqual(self.get(limit=10, mentor_id=self.fixture.student.id).status_code, 400)
        token = create_access_token(identity=self.fixture.student.email)
        with patch('services.auth_context.current_actor',
                   return_value=SimpleNamespace(user=self.fixture.student)):
            result = self.client.get(f'/camp/sessions/{self.sid}/meetings/all?limit=10',
                                     headers={'Authorization': 'Bearer ' + token})
        self.assertEqual(result.status_code, 403)


if __name__ == '__main__':
    unittest.main(verbosity=2)
