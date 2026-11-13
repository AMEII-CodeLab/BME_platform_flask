"""Serve real meeting/progress blueprints with disposable in-memory SQLite only."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    os.chdir(ROOT)
    os.environ['JWT_SECRET'] = 'isolated-meeting-browser-contract-only-20261114'
    from flask import jsonify
    from datetime import date
    from exts import db
    from models import CampMeeting
    from test_camp_meeting_overview import MeetingOverviewTest

    fixture = MeetingOverviewTest()
    fixture.setUp()
    actor = fixture.fixture
    for day in range(1, 10):
        db.session.add(CampMeeting(camp_session_id=fixture.sid, scope='team',
            mentor_id=fixture.owner_id, title=f'Additional meeting {day}',
            meeting_date=date(2026, 11, day), created_by=fixture.owner_id))
    db.session.commit()

    @actor.app.get('/audit/session')
    def session():
        return jsonify(token=fixture.headers['Authorization'].removeprefix('Bearer '),
                       sid=fixture.sid, mentor_name=actor.owner.username)

    try:
        actor.app.run(host='127.0.0.1', port=5014, threaded=False, use_reloader=False)
    finally:
        fixture.tearDown()


if __name__ == '__main__':
    main()
