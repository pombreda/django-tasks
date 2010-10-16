#
# Copyright (c) 2010 by nexB, Inc. http://www.nexb.com/ - All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
# 
#     1. Redistributions of source code must retain the above copyright notice,
#        this list of conditions and the following disclaimer.
#    
#     2. Redistributions in binary form must reproduce the above copyright
#        notice, this list of conditions and the following disclaimer in the
#        documentation and/or other materials provided with the distribution.
# 
#     3. Neither the names of Django, nexB, Django-tasks nor the names of the contributors may be used
#        to endorse or promote products derived from this software without
#        specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from __future__ import with_statement 

import sys
import StringIO
import os
import unittest
import tempfile
import time
import inspect
import logging
from os.path import join, dirname, basename, exists, join

import re
DATETIME_REGEX = re.compile('([a-zA-Z]+[.]? \d+\, \d\d\d\d at \d+(\:\d+)? [ap]\.m\.)|( \((\d+ hour(s)?(, )?)?(\d+ minute(s)?(, )?)?(\d+ second(s)?(, )?)?\))')

from models import Task, TaskManager, LOG

class LogCheck(object):
    def __init__(self, test, expected_log = None, fail_if_different=True):
        self.test = test
        self.expected_log = expected_log or ''
        self.fail_if_different = fail_if_different
        
    def __enter__(self):
        self.loghandlers = LOG.handlers
        LOG.handlers = []
        self.log = StringIO.StringIO()
        test_handler = logging.StreamHandler(self.log)
        test_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        LOG.addHandler(test_handler)
        
    def __exit__(self, type, value, traceback):
        # Restore state
        self.loghandlers = LOG.handlers

        # Check the output only if no exception occured (to avoid "eating" test failures)
        if type:
            return
        
        if self.fail_if_different:
            self.test.assertEquals(self.expected_log, self.log.getvalue())


class TestModel(object):
    ''' A mock Model object for task tests'''
    class Manager(object):
        def get(self, pk):
            if basename(pk) not in ['key1', 'key2', 'key3', 'key with space', 'key-more']:
                raise Exception("Not a good object loaded")
            return TestModel(pk)

    objects = Manager()
    def __init__(self, pk):
        self.pk = pk

    def _run(self, trigger_name, sleep=0.2):
        print "running %s" % trigger_name
        sys.stdout.flush()
        time.sleep(sleep)
        self._trigger(trigger_name)

    def run_something_long(self, msg=''):
        self._run("run_something_long_1", 0.0) # trigger right away, 
        time.sleep(0.2) # then sleep
        self._run("run_something_long_2")
        return "finished"
    
    def run_something_else(self):
        pass

    def run_something_failing(self):
        self._run("run_something_failing")
        raise Exception("Failed !")

    def run_something_with_required(self):
        self._run("run_something_with_required")
        return "finished required"

    def run_something_with_required_failing(self):
        self._run("run_something_with_required")
        return "finished required"

    def run_something_with_two_required(self):
        self._run("run_something_with_two_required")
        return "finished run_something_with_two_required"

    def run_something_with_required_with_two_required(self):
        self._run("run_something_with_required_with_two_required")
        return "finished required with required"

    def run_a_method_that_is_not_registered(self):
        # not called in the tests
        pass

    def run_something_fast(self):
        self._run("run_something_fast", 0.1)

    def check_database_settings(self):
        from django.db import connection
        print connection.settings_dict["NAME"]
        time.sleep(0.1)
        self._trigger("check_database_settings")

    def _trigger(self, event):
        open(self.pk + event, 'w').writelines(["."])

def _start_message(task):
    return "INFO: Starting task " + str(task.pk) + "...\nINFO: ...Task " + str(task.pk) + " started.\n" 
    
TEST_DEFINED_TASKS = [
    ('run_something_long', "Run a successful task", ''),
    ('run_something_else', "Run an empty task", ''),
    ('run_something_failing', "Run a failing task", ''),
    ('run_something_with_required', "Run a task with a required task", 'run_something_long'),
    ('run_something_with_two_required', "Run a task with two required task", 'run_something_long,run_something_with_required'),
    ('run_something_fast', "Run a fast task", ''),
    ('run_something_with_required_failing', "Run a task with a required task that fails", 'run_something_failing'),
    ('run_something_with_required_with_two_required', "Run a task with a required task that has a required task", "run_something_with_two_required"),
    ('check_database_settings', "Checks the database settings", ''),
    ]

class ViewsTestCase(unittest.TestCase):
    def failUnlessRaises(self, excClassOrInstance, callableObj, *args, **kwargs):
        # improved method compared to unittest.TestCase.failUnlessRaises:
        # also check the content of the exception
        if inspect.isclass(excClassOrInstance):
            return unittest.TestCase.failUnlessRaises(self, excClassOrInstance, callableObj, *args, **kwargs)

        excClass = excClassOrInstance.__class__
        try:
            callableObj(*args, **kwargs)
        except excClass, e:
            self.assertEquals(str(excClassOrInstance), str(e))
        else:
            if hasattr(excClass,'__name__'): excName = excClass.__name__
            else: excName = str(excClass)
            raise self.failureException, "%s not raised" % excName

    assertRaises = failUnlessRaises

    def setUp(self):
        TaskManager.DEFINED_TASKS['djangotasks.tests.TestModel'] = TEST_DEFINED_TASKS
        import tempfile
        self.tempdir = tempfile.mkdtemp()
        import os
        os.environ['DJANGOTASKS_TESTING'] = "YES"

    def tearDown(self):
        del TaskManager.DEFINED_TASKS['djangotasks.tests.TestModel']
        for task in Task.objects.filter(model='djangotasks.tests.TestModel'):
            task.delete()
        import shutil
        shutil.rmtree(self.tempdir)
        import os
        del os.environ['DJANGOTASKS_TESTING']

    #  This may be needed for databases that can't share transactions (connections) accross threads (sqlite in particular):
    #  the tests tasks may need to be commited before the execution thread is started, which require transaction.commit to actually *do* the commit --
    #  and the original "_fixture_setup" causes "transaction.commit" to be transformed into a "nop" !!!
    #def _fixture_setup(self):
    #    pass
    #def _fixture_teardown(self):
    #    pass

    def test_tasks_import(self):
        from djangotasks.models import _my_import
        self.assertEquals(TestModel, _my_import('djangotasks.tests.TestModel'))

    def _create_task(self, method, object_id):
        from djangotasks.models import _qualified_class_name
        return Task.objects._create_task(_qualified_class_name(method.im_class), 
                                         method.im_func.__name__, 
                                         object_id)


    def test_tasks_invalid_method(self):
        self.assertRaises(Exception("Method 'run_a_method_that_is_not_registered' not registered for model 'djangotasks.tests.TestModel'"), 
                          self._create_task, TestModel.run_a_method_that_is_not_registered, 'key1')

        class NotAValidModel(object):
            def a_method(self):
                pass
        self.assertRaises(Exception("'module' object has no attribute 'NotAValidModel'"), 
                          self._create_task, NotAValidModel.a_method, 'key1')
            
        self.assertRaises(Exception("Not a good object loaded"), 
                          self._create_task, TestModel.run_something_long, 'key_that_does_not_exist')

    def test_tasks_register(self):
        class MyClass(object):
            def mymethod1(self):
                pass

            def mymethod2(self):
                pass
            
            def mymethod3(self):
                pass
                
            def mymethod4(self):
                pass

            def mymethod5(self):
                pass
                
        from djangotasks.models import register_task
        try:
            register_task(MyClass.mymethod1, '''Some documentation''')
            register_task(MyClass.mymethod2, '''Some other documentation''', MyClass.mymethod1)
            register_task(MyClass.mymethod3, None, MyClass.mymethod1, MyClass.mymethod2)
            register_task(MyClass.mymethod4, None, [MyClass.mymethod1, MyClass.mymethod2])
            register_task(MyClass.mymethod5, None, (MyClass.mymethod1, MyClass.mymethod2))
            self.assertEquals([('mymethod1', 'Some documentation', ''), 
                               ('mymethod2', 'Some other documentation', 'mymethod1'),
                               ('mymethod3', '', 'mymethod1,mymethod2'),
                               ('mymethod4', '', 'mymethod1,mymethod2'),
                               ('mymethod5', '', 'mymethod1,mymethod2'),                               
                              ],
                              TaskManager.DEFINED_TASKS['djangotasks.tests.MyClass'])
        finally:
            del TaskManager.DEFINED_TASKS['djangotasks.tests.MyClass']

    def _wait_until(self, key, event):
        max = 100 # 10 seconds; on slow, loaded, Mac machines, a lower value doesn't seem to be enough
        while not exists(join(self.tempdir, key + event)) and max:
            time.sleep(0.1)
            max -= 1
        if not max:
            self.fail("Timeout on key=%s, event=%s" % (key, event))
        
    def _reset(self, key, event):
        os.remove(join(self.tempdir, key + event))

    def _assert_status(self, expected_status, task):
        task = Task.objects.get(pk=task.pk)
        self.assertEquals(expected_status, task.status)

    def test_tasks_run_successful(self):
        task = self._create_task(TestModel.run_something_long, join(self.tempdir, 'key1'))
        Task.objects.run_task(task.pk)
        with LogCheck(self, _start_message(task)):
            Task.objects._do_schedule()
        self._wait_until('key1', 'run_something_long_2')
        time.sleep(0.5)
        new_task = Task.objects.get(pk=task.pk)
        self.assertEquals(u'running run_something_long_1\nrunning run_something_long_2\n'
                          , new_task.log)
        self.assertEquals("successful", new_task.status)

    def test_tasks_run_check_database(self):
        task = self._create_task(TestModel.check_database_settings, join(self.tempdir, 'key1'))
        Task.objects.run_task(task.pk)
        with LogCheck(self, _start_message(task)):
            Task.objects._do_schedule()
        self._wait_until('key1', 'check_database_settings')
        time.sleep(0.5)
        new_task = Task.objects.get(pk=task.pk)
        from django.db import connection
        self.assertEquals(connection.settings_dict["NAME"] + u'\n' , new_task.log) # May fail if your Django settings define a different test database for each run: in which case you should modify it, to ensure it's always the same.
        self.assertEquals("successful", new_task.status)

    def test_tasks_run_with_space_fast(self):
        task = self._create_task(TestModel.run_something_fast, join(self.tempdir, 'key with space'))
        Task.objects.run_task(task.pk)
        with LogCheck(self, _start_message(task)):
            Task.objects._do_schedule()
        self._wait_until('key with space', "run_something_fast")
        time.sleep(0.5)
        new_task = Task.objects.get(pk=task.pk)
        self.assertEquals(u'running run_something_fast\n'
                          , new_task.log)
        self.assertEquals("successful", new_task.status)

    def test_tasks_run_cancel_running(self):
        task = self._create_task(TestModel.run_something_long, join(self.tempdir, 'key1'))
        Task.objects.run_task(task.pk)
        with LogCheck(self, _start_message(task)):
            Task.objects._do_schedule()
        self._wait_until('key1', "run_something_long_1")
        Task.objects.cancel_task(task.pk)
        output_check = LogCheck(self, fail_if_different=False)
        with output_check:
            Task.objects._do_schedule()
            time.sleep(0.3)
        self.assertTrue(("Cancelling task " + str(task.pk) + "...") in output_check.log.getvalue())
        self.assertTrue("cancelled.\n" in output_check.log.getvalue())
        #self.assertTrue('INFO: failed to mark tasked as finished, from status "running" to "unsuccessful" for task 3. May have been finished in a different thread already.\n'
        #                in output_check.log.getvalue())

        new_task = Task.objects.get(pk=task.pk)
        self.assertEquals("cancelled", new_task.status)
        self.assertTrue(u'running run_something_long_1' in new_task.log)
        self.assertFalse(u'running run_something_long_2' in new_task.log)
        self.assertFalse('finished' in new_task.log)

    def test_tasks_run_cancel_scheduled(self):
        task = self._create_task(TestModel.run_something_long, join(self.tempdir, 'key1'))
        with LogCheck(self):
            Task.objects._do_schedule()
        Task.objects.run_task(task.pk)
        Task.objects.cancel_task(task.pk)
        with LogCheck(self, "INFO: Cancelling task " + str(task.pk) + "...\nINFO: Task " + str(task.pk) + " finished with status \"cancelled\"\nINFO: ...Task " + str(task.pk) + " cancelled.\n"):
            Task.objects._do_schedule()
        new_task = Task.objects.get(pk=task.pk)
        self.assertEquals("cancelled", new_task.status)            
        self.assertEquals("", new_task.log)

    def test_tasks_run_failing(self):
        task = self._create_task(TestModel.run_something_failing, join(self.tempdir, 'key1'))
        Task.objects.run_task(task.pk)
        with LogCheck(self, _start_message(task)):
            Task.objects._do_schedule()
        self._wait_until('key1', "run_something_failing")
        time.sleep(0.5)
        new_task = Task.objects.get(pk=task.pk)
        self.assertEquals("unsuccessful", new_task.status)
        self.assertTrue(u'running run_something_failing' in new_task.log)
        self.assertTrue(u'raise Exception("Failed !")' in new_task.log)
        self.assertTrue(u'Exception: Failed !' in new_task.log)
    
    def test_tasks_get_tasks_for_object(self):
        tasks = Task.objects.tasks_for_object(TestModel, 'key2')
        self.assertEquals(len(TEST_DEFINED_TASKS), len(tasks))
        self.assertEquals('defined', tasks[0].status)
        self.assertEquals('defined', tasks[1].status)
        self.assertEquals('run_something_long', tasks[0].method)
        self.assertEquals('run_something_else', tasks[1].method)

    def test_tasks_get_task_for_object(self):
        self.assertRaises(Exception("Method 'run_doesn_not_exists' not registered for model 'djangotasks.tests.TestModel'"), 
                          Task.objects.task_for_object, TestModel, 'key2', 'run_doesn_not_exists')
        task = Task.objects.task_for_object(TestModel, 'key2', 'run_something_long')
        self.assertEquals('defined', task.status)
        self.assertEquals('run_something_long', task.method)

    def test_tasks_get_task_for_object_required(self):
        task = Task.objects.task_for_object(TestModel, 'key-more', 'run_something_with_two_required')
        self.assertEquals(['run_something_long', 'run_something_with_required'], 
                          [required_task.method for required_task in task.get_required_tasks()])
        
    def test_tasks_archive_task(self):
        tasks = Task.objects.tasks_for_object(TestModel, 'key3')
        task = tasks[0]
        self.assertTrue(task.pk)
        task.status = 'successful'
        task.save()
        self.assertEquals(False, task.archived)
        new_task = self._create_task(TestModel.run_something_long,
                                     'key3')
        self.assertTrue(new_task.pk)
        self.assertTrue(task.pk != new_task.pk)
        old_task = Task.objects.get(pk=task.pk)        
        self.assertEquals(True, old_task.archived, "Task should have been archived once a new one has been created")

    def test_tasks_get_required_tasks(self):
        task = self._create_task(TestModel.run_something_with_required, 'key1')
        self.assertEquals(['run_something_long'],
                          [required_task.method for required_task in task.get_required_tasks()])
        
        
        task = self._create_task(TestModel.run_something_with_two_required, 'key1')
        self.assertEquals(['run_something_long', 'run_something_with_required'],
                          [required_task.method for required_task in task.get_required_tasks()])

    def _check_running(self, key, current_task, previous_task, task_name):
        self._assert_status("scheduled", current_task)
        with LogCheck(self, _start_message(current_task)):
            Task.objects._do_schedule()
        time.sleep(0.1)
        self._assert_status("running", current_task)
        if previous_task:
            self._assert_status("successful", previous_task)
        self._wait_until(key, task_name)
        time.sleep(0.5)
        self._assert_status("successful", current_task)

    def test_tasks_run_required_task_successful(self):
        required_task = Task.objects.task_for_object(TestModel, join(self.tempdir, 'key1'), 'run_something_long')
        task = self._create_task(TestModel.run_something_with_required, join(self.tempdir, 'key1'))
        self.assertEquals("defined", required_task.status)

        Task.objects.run_task(task.pk)
        self._assert_status("scheduled", task)
        self._assert_status("scheduled", required_task)

        self._check_running('key1', required_task, None, 'run_something_long_2')
        self._check_running('key1', task, required_task, 'run_something_with_required')

        task = Task.objects.get(pk=task.pk)
        complete_log, _ = DATETIME_REGEX.subn('', task.complete_log())

        self.assertEquals(u'Run a successful task started on \n' + 
                          u'running run_something_long_1\n' + 
                          u'running run_something_long_2\n' + 
                          u'\n' + 
                          u'Run a successful task finished successfully on \n' + 
                          u'Run a task with a required task started on \n' + 
                          u'running run_something_with_required\n' + 
                          u'\n' + 
                          u'Run a task with a required task finished successfully on ', complete_log)

    def test_tasks_run_two_required_tasks_successful(self):
        key = join(self.tempdir, 'key2')
        required_task = Task.objects.task_for_object(TestModel, key, 'run_something_long')
        with_required_task = Task.objects.task_for_object(TestModel, key, 'run_something_with_required')
        task = self._create_task(TestModel.run_something_with_two_required, key)
        self.assertEquals("defined", required_task.status)

        Task.objects.run_task(task.pk)
        self._assert_status("scheduled", task)
        self._assert_status("scheduled", required_task)

        self._check_running('key2', required_task, None, 'run_something_long_2')
        self._check_running('key2', with_required_task, required_task, 'run_something_with_required')
        self._check_running('key2', task, with_required_task, 'run_something_with_two_required')

        task = Task.objects.get(pk=task.pk)
        complete_log, _ = DATETIME_REGEX.subn('', task.complete_log())

        self.assertEquals(u'Run a successful task started on \n' + 
                          u'running run_something_long_1\n' + 
                          u'running run_something_long_2\n' + 
                          u'\n' + 
                          u'Run a successful task finished successfully on \n' + 
                          u'Run a task with a required task started on \n' + 
                          u'running run_something_with_required\n' + 
                          u'\n' + 
                          u'Run a task with a required task finished successfully on \n' + 
                          u'Run a task with two required task started on \n' + 
                          u'running run_something_with_two_required\n' + 
                          u'\n' + 
                          u'Run a task with two required task finished successfully on ',
                          complete_log)

    def test_tasks_run_required_with_two_required_tasks_successful(self):
        key = join(self.tempdir, 'key3')
        required_task = Task.objects.task_for_object(TestModel, key, 'run_something_long')
        with_required_task = Task.objects.task_for_object(TestModel, key, 'run_something_with_required')
        with_two_required_task = Task.objects.task_for_object(TestModel, key, 'run_something_with_two_required')
        task = self._create_task(TestModel.run_something_with_required_with_two_required, key)
        self.assertEquals("defined", required_task.status)

        Task.objects.run_task(task.pk)

        self._assert_status("scheduled", task)
        self._assert_status("scheduled", with_required_task)
        self._assert_status("scheduled", with_two_required_task)
        self._assert_status("scheduled", required_task)

        self._check_running('key3', required_task, None, 'run_something_long_2')
        self._check_running('key3', with_required_task, required_task, "run_something_with_required")
        self._check_running('key3', with_two_required_task, with_required_task, "run_something_with_two_required")
        self._check_running('key3', task, with_two_required_task, "run_something_with_required_with_two_required")

        task = Task.objects.get(pk=task.pk)
        complete_log, _ = DATETIME_REGEX.subn('', task.complete_log())

        self.assertEquals(u'Run a successful task started on \n' + 
                          u'running run_something_long_1\n' + 
                          u'running run_something_long_2\n' + 
                          u'\n' + 
                          u'Run a successful task finished successfully on \n' + 
                          u'Run a task with a required task started on \n' + 
                          u'running run_something_with_required\n' + 
                          u'\n' + 
                          u'Run a task with a required task finished successfully on \n' + 
                          u'Run a task with two required task started on \n' + 
                          u'running run_something_with_two_required\n' + 
                          u'\n' + 
                          u'Run a task with two required task finished successfully on \n' + 
                          u'Run a task with a required task that has a required task started on \n' + 
                          u'running run_something_with_required_with_two_required\n' + 
                          u'\n' + 
                          u'Run a task with a required task that has a required task finished successfully on ',
                          complete_log)

    def test_tasks_run_required_task_failing(self):
        required_task = Task.objects.task_for_object(TestModel, join(self.tempdir, 'key1'), 'run_something_failing')
        task = self._create_task(TestModel.run_something_with_required_failing, join(self.tempdir, 'key1'))
        self.assertEquals("defined", required_task.status)

        Task.objects.run_task(task.pk)
        self._assert_status("scheduled", task)
        self._assert_status("scheduled", required_task)

        with LogCheck(self, _start_message(required_task)):
            Task.objects._do_schedule()
        time.sleep(0.5)
        self._assert_status("scheduled", task)
        self._assert_status("running", required_task)

        self._wait_until('key1', 'run_something_failing')
        time.sleep(0.5)
        self._assert_status("scheduled", task)
        self._assert_status("unsuccessful", required_task)

        with LogCheck(self):
            Task.objects._do_schedule()
        time.sleep(0.5)
        self._assert_status("unsuccessful", task)
        task = Task.objects.get(pk=task.pk)

        complete_log, _ = DATETIME_REGEX.subn('', task.complete_log())
        self.assertTrue(complete_log.startswith('Run a failing task started on \nrunning run_something_failing\nTraceback (most recent call last):'))
        self.assertTrue(complete_log.endswith(u', in run_something_failing\n    raise Exception("Failed !")\nException: Failed !\n\n' + 
                                              u'Run a failing task finished with error on \n' + 
                                              u'Run a task with a required task that fails started\n' + 
                                              u'Run a task with a required task that fails finished with error'))
        self.assertEquals("unsuccessful", task.status)

    def test_tasks_run_again(self):
        tasks = Task.objects.tasks_for_object(TestModel, join(self.tempdir, 'key1'))
        task = tasks[5]
        self.assertEquals('run_something_fast', task.method)
        Task.objects.run_task(task.pk)
        with LogCheck(self, _start_message(task)):
            Task.objects._do_schedule()
        self._wait_until('key1', "run_something_fast")
        time.sleep(0.5)
        self._reset('key1', "run_something_fast")
        self._assert_status("successful", task)
        Task.objects.run_task(task.pk)
        output_check = LogCheck(self, fail_if_different=False)
        with output_check:
            Task.objects._do_schedule()
        self._wait_until('key1', "run_something_fast")
        time.sleep(0.5)
        import re
        pks = re.findall(r'(\d+)', output_check.log.getvalue())
        new_task = Task.objects.get(pk=int(pks[0]))
        self.assertEquals(_start_message(new_task) + 'INFO: Task ' + str(new_task.pk) + ' finished with status "successful"\n', 
                          output_check.log.getvalue())
        self.assertTrue(new_task.pk != task.pk)
        self.assertEquals("successful", new_task.status)
        tasks = Task.objects.tasks_for_object(TestModel, join(self.tempdir, 'key1'))
        self.assertEquals(new_task.pk, tasks[5].pk)
        

    def test_tasks_exception_in_thread(self):
        task = self._create_task(TestModel.run_something_long, join(self.tempdir, 'key1'))
        Task.objects.run_task(task.pk)
        task = self._create_task(TestModel.run_something_long, join(self.tempdir, 'key1'))
        task_delete = self._create_task(TestModel.run_something_long, join(self.tempdir, 'key1'))
        task_delete.delete()
        try:
            Task.objects.get(pk=task.pk)
            self.fail("Should throw an exception")
        except Exception, e:
            self.assertEquals("Task matching query does not exist.", str(e))
            
        with LogCheck(self, 'WARNING: Failed to change status from "scheduled" to "running" for task %d\n' % task.pk):
            task.do_run()
            time.sleep(0.5)

    def test_compute_duration(self):
        from datetime import datetime
        task = Task.objects.tasks_for_object(TestModel, 'key1')[0]
        task.start_date = datetime(2010, 10, 7, 14, 22, 17, 848801)
        task.end_date = datetime(2010, 10, 7, 17, 23, 43, 933740)
        self.assertEquals('3 hours, 1 minute, 26 seconds', task.duration)
        task.end_date = datetime(2010, 10, 7, 15, 12, 18, 933740)
        self.assertEquals('50 minutes, 1 second', task.duration)
        task.end_date = datetime(2010, 10, 7, 15, 22, 49, 933740)
        self.assertEquals('1 hour, 32 seconds', task.duration)
        task.end_date = datetime(2010, 10, 7, 14, 22, 55, 933740)
        self.assertEquals('38 seconds', task.duration)
