"""Explicit local MySQL QA; normal unittest discovery never connects or reads .env.

Set BME_TEST_MYSQL_URI explicitly. Only localhost / 127.0.0.1 is allowed;
this script creates and removes its own randomly named QA database.
"""
import json
import os
import sys
import uuid
import threading
from datetime import date
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pymysql
from sqlalchemy.engine import URL, make_url


def main():
    raw_uri = os.environ.get('BME_TEST_MYSQL_URI', '')
    if not raw_uri:
        raise SystemExit('请显式提供本机隔离测试连接 BME_TEST_MYSQL_URI，不读取业务 .env')
    url = make_url(raw_uri)
    if url.get_backend_name() != 'mysql' or url.host not in ('localhost', '127.0.0.1'):
        raise SystemExit('只允许 localhost / 127.0.0.1 的 MySQL 测试服务')
    if url.database and not url.database.startswith('bme_project_test_'):
        raise SystemExit('测试连接不能指定业务库，请留空库名或使用 bme_project_test_ 前缀')
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    os.environ['JWT_SECRET']='isolated-project-core-mysql-qa-secret-20261017'
    os.environ['IDENTITY_ENFORCEMENT_MODE']='off';os.environ['IDENTITY_VERIFY_GATE_DEFAULT']='off'
    os.environ['PROJECT_CORE_ENABLED']='true'
    from flask import Flask
    from exts import db
    import config,models as m
    from project_models import PROJECT_CORE_TABLES
    from group_models import GROUP_CORE_TABLES
    from services.projects import core,records
    from services.groups import GroupError
    name='bme_project_core_qa_'+uuid.uuid4().hex[:12]
    connection=pymysql.connect(host=url.host,port=url.port or 3306,user=url.username,password=url.password,autocommit=True)
    created=False;engine=None
    try:
        with connection.cursor() as cursor:cursor.execute('CREATE DATABASE `'+name+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
        created=True
        uri=URL.create('mysql+pymysql',username=url.username,password=url.password,host=url.host,port=url.port or 3306,database=name,query={'charset':'utf8mb4'})
        app=Flask(__name__);app.config.from_object(config);app.config.update(SQLALCHEMY_DATABASE_URI=uri,PROJECT_CORE_ENABLED=True)
        db.init_app(app)
        with app.app_context():
            engine=db.engine;tables=set()
            def include(table):
                if table in tables:return
                tables.add(table)
                for fk in table.foreign_keys:include(fk.column.table)
            for table in tuple(PROJECT_CORE_TABLES)+tuple(GROUP_CORE_TABLES):include(table)
            include(m.NotificationModel.__table__)
            db.metadata.create_all(engine,tables=list(tables))
            # 再次执行新表的逐表创建，验证发布脚本采用的幂等次序。
            for table in PROJECT_CORE_TABLES:table.create(engine,checkfirst=True)
            owner=m.UserModel(username='并发检查负责人',email='owner@mysql-qa.invalid',password='local-qa-only',role='user',status='active',lifecycle='active',account_kind='standard')
            db.session.add(owner);db.session.commit();uid=owner.id
            pid=core.create(owner,{'title':'并发版本检查','idempotency_key':'initial-create'})['project']['id'];db.session.commit()
        def concurrent(worker,user_ids=None):
            barrier=threading.Barrier(2)
            def wrapped(index):
                with app.app_context():
                    user=db.session.get(m.UserModel,(user_ids or [uid,uid])[index])
                    barrier.wait(timeout=10)
                    try:
                        value=worker(user,index);db.session.commit();return {'ok':True,'value':value}
                    except GroupError as exc:db.session.rollback();return {'ok':False,'machine':exc.machine}
                    finally:db.session.remove()
            with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(wrapped,[0,1]))
        cas=concurrent(lambda u,i:core.update(u,pid,{'title':'版本'+str(i),'expected_version':1,'reason':'真实MySQL并发版本检查','idempotency_key':'cas-'+str(i)}))
        assert sum(r['ok'] for r in cas)==1,cas
        assert any(r.get('machine')=='PROJECT_VERSION_CONFLICT' for r in cas),cas
        replay=concurrent(lambda u,i:core.create(u,{'title':'同键并发创建','idempotency_key':'same-create-key'}))
        assert all(r['ok'] for r in replay),replay
        assert replay[0]['value']['project']['id']==replay[1]['value']['project']['id'],replay
        with app.app_context():
            assert m.Project.query.count()==2
            student=m.UserModel(username='并发检查成员',email='member@mysql-qa.invalid',password='local-qa-only',role='user',status='active',lifecycle='active',account_kind='standard')
            db.session.add(student);db.session.commit();student_id=student.id
            project=db.session.get(m.Project,pid)
            core.change_member(db.session.get(m.UserModel,uid),pid,{'action':'add','user_id':student_id,'expected_version':project.version,'reason':'并发通知检查','idempotency_key':'add-concurrent-member'})
            db.session.commit();version=project.version
        cross_user=concurrent(lambda u,i:records.save(u,pid,{'kind':'record','title':'并发记录'+str(i),'occurred_on':date.today().isoformat(),'reason':'真实MySQL不同成员同时写入及通知','expected_version':version,'idempotency_key':'record-'+str(i)},[],[]),[uid,student_id])
        assert sum(r['ok'] for r in cross_user)==1,cross_user
        assert any(r.get('machine')=='PROJECT_VERSION_CONFLICT' for r in cross_user),cross_user
        with app.app_context():
            assert m.ProjectRecord.query.count()==1
            assert m.NotificationModel.query.filter_by(source_type='project_core').count()==1
            print(json.dumps({'new_tables':len(PROJECT_CORE_TABLES),'dependency_tables':len(tables),'ddl_and_repeat_create':'passed','concurrent_version':'one success, one conflict','concurrent_idempotent_create':'same project returned','concurrent_cross_member_record_and_notification':'passed without deadlock','temporary_database_removed_after_check':True},ensure_ascii=False))
    finally:
        if engine:engine.dispose()
        if created:
            with connection.cursor() as cursor:cursor.execute('DROP DATABASE `'+name+'`')
        connection.close()


if __name__ == '__main__':
    main()
