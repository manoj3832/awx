# Copyright (c) 2015 Ansible, Inc.
# All Rights Reserved

# Python
from __future__ import absolute_import
import os
import unittest2 as unittest

# Django
import django
from django.core.urlresolvers import reverse

# AWX
from awx.main.models import * # noqa
from awx.main.tests.job_base import BaseJobTestMixin
import yaml

__all__ = ['JobTemplateLaunchTest', 'JobTemplateLaunchPasswordsTest']


@unittest.skipIf(os.environ.get('SKIP_SLOW_TESTS', False), 'Skipping slow test')
class JobTemplateLaunchTest(BaseJobTestMixin, django.test.TransactionTestCase):
    def setUp(self):
        super(JobTemplateLaunchTest, self).setUp()

        self.url = reverse('api:job_template_list')
        self.data = dict(
            name         = 'launched job template',
            job_type     = PERM_INVENTORY_DEPLOY,
            inventory    = self.inv_eng.pk,
            project      = self.proj_dev.pk,
            credential   = self.cred_sue.pk,
            playbook     = self.proj_dev.playbooks[0],
            ask_variables_on_launch = True,
            ask_credential_on_launch = True,
        )
        self.data_no_cred = dict(
            name         = 'launched job template no credential',
            job_type     = PERM_INVENTORY_DEPLOY,
            inventory    = self.inv_eng.pk,
            project      = self.proj_dev.pk,
            playbook     = self.proj_dev.playbooks[0],
            ask_credential_on_launch = True,
            ask_variables_on_launch = True,
        )
        self.data_cred_ask = dict(self.data)
        self.data_cred_ask['name'] = 'launched job templated with ask passwords'
        self.data_cred_ask['credential'] = self.cred_sue_ask.pk

        with self.current_user(self.user_sue):
            response = self.post(self.url, self.data, expect=201)
            self.launch_url = reverse('api:job_template_launch',
                                      args=(response['id'],))

    def test_launch_job_template(self):
        with self.current_user(self.user_sue):
            self.data['name'] = 'something different'
            response = self.post(self.url, self.data, expect=201)
            detail_url = reverse('api:job_template_detail',
                                 args=(response['id'],))
            self.assertEquals(response['url'], detail_url)

    def test_no_cred_update_template(self):
        # You can still post the job template without a credential, just can't launch it without one
        with self.current_user(self.user_sue):
            response = self.post(self.url, self.data_no_cred, expect=201)
            detail_url = reverse('api:job_template_detail',
                                 args=(response['id'],))
            self.assertEquals(response['url'], detail_url)

    def test_invalid_auth_unauthorized(self):
        # Invalid auth can't trigger the launch endpoint
        self.check_invalid_auth(self.launch_url, {}, methods=('post',))

    def test_credential_implicit(self):
        # Implicit, attached credentials
        with self.current_user(self.user_sue):
            response = self.post(self.launch_url, {}, expect=201)
            j = Job.objects.get(pk=response['job'])
            self.assertTrue(j.status == 'new')

    def test_launch_extra_vars_json(self):
        # Sending extra_vars as a JSON string, implicit credentials
        with self.current_user(self.user_sue):
            data = dict(extra_vars = '{\"a\":3}')
            response = self.post(self.launch_url, data, expect=201)
            j = Job.objects.get(pk=response['job'])
            ev_dict = yaml.load(j.extra_vars)
            self.assertIn('a', ev_dict)
            if 'a' in ev_dict:
                self.assertEqual(ev_dict['a'], 3)

    def test_launch_extra_vars_yaml(self):
        # Sending extra_vars as a JSON string, implicit credentials
        with self.current_user(self.user_sue):
            data = dict(extra_vars = 'a: 3')
            response = self.post(self.launch_url, data, expect=201)
            j = Job.objects.get(pk=response['job'])
            ev_dict = yaml.load(j.extra_vars)
            self.assertIn('a', ev_dict)
            if 'a' in ev_dict:
                self.assertEqual(ev_dict['a'], 3)

    def test_credential_explicit(self):
        # Explicit, credential
        with self.current_user(self.user_sue):
            self.cred_sue.delete()
            response = self.post(self.launch_url, {'credential': self.cred_doug.pk}, expect=201)
            j = Job.objects.get(pk=response['job'])
            self.assertEqual(j.status, 'new')
            self.assertEqual(j.credential.pk, self.cred_doug.pk)

    def test_credential_explicit_via_credential_id(self):
        # Explicit, credential
        with self.current_user(self.user_sue):
            self.cred_sue.delete()
            response = self.post(self.launch_url, {'credential_id': self.cred_doug.pk}, expect=201)
            j = Job.objects.get(pk=response['job'])
            self.assertEqual(j.status, 'new')
            self.assertEqual(j.credential.pk, self.cred_doug.pk)

    def test_credential_override(self):
        # Explicit, credential
        with self.current_user(self.user_sue):
            response = self.post(self.launch_url, {'credential': self.cred_doug.pk}, expect=201)
            j = Job.objects.get(pk=response['job'])
            self.assertEqual(j.status, 'new')
            self.assertEqual(j.credential.pk, self.cred_doug.pk)

    def test_credential_override_via_credential_id(self):
        # Explicit, credential
        with self.current_user(self.user_sue):
            response = self.post(self.launch_url, {'credential_id': self.cred_doug.pk}, expect=201)
            j = Job.objects.get(pk=response['job'])
            self.assertEqual(j.status, 'new')
            self.assertEqual(j.credential.pk, self.cred_doug.pk)

    def test_bad_credential_launch_fail(self):
        # Can't launch a job template without a credential defined (or if we
        # pass an invalid/inactive credential value).
        with self.current_user(self.user_sue):
            self.cred_sue.delete()
            self.post(self.launch_url, {}, expect=400)
            self.post(self.launch_url, {'credential': 0}, expect=400)
            self.post(self.launch_url, {'credential_id': 0}, expect=400)
            self.post(self.launch_url, {'credential': 'one'}, expect=400)
            self.post(self.launch_url, {'credential_id': 'one'}, expect=400)
            cred_doug_pk = self.cred_doug.pk
            self.cred_doug.delete()
            self.post(self.launch_url, {'credential': cred_doug_pk}, expect=400)
            self.post(self.launch_url, {'credential_id': cred_doug_pk}, expect=400)

    def test_explicit_unowned_cred(self):
        # Explicitly specify a credential that we don't have access to
        with self.current_user(self.user_juan):
            launch_url = reverse('api:job_template_launch',
                                 args=(self.jt_eng_run.pk,))
            self.post(launch_url, {'credential_id': self.cred_sue.pk}, expect=403)

    def test_no_project_fail(self):
        # Job Templates without projects cannot be launched
        with self.current_user(self.user_sue):
            self.data['name'] = "missing proj"
            response = self.post(self.url, self.data, expect=201)
            jt = JobTemplate.objects.get(pk=response['id'])
            jt.project = None
            jt.save()
            launch_url2 = reverse('api:job_template_launch',
                                  args=(response['id'],))
            self.post(launch_url2, {}, expect=400)

    def test_no_inventory_fail(self):
        # Job Templates without inventory cannot be launched
        with self.current_user(self.user_sue):
            self.data['name'] = "missing inv"
            response = self.post(self.url, self.data, expect=201)
            jt = JobTemplate.objects.get(pk=response['id'])
            jt.inventory = None
            jt.save()
            launch_url3 = reverse('api:job_template_launch',
                                  args=(response['id'],))
            self.post(launch_url3, {}, expect=400)

    def test_deleted_credential_fail(self):
        # Job Templates with deleted credentials cannot be launched.
        self.cred_sue.delete()
        with self.current_user(self.user_sue):
            self.post(self.launch_url, {}, expect=400)


@unittest.skipIf(os.environ.get('SKIP_SLOW_TESTS', False), 'Skipping slow test')
class JobTemplateLaunchPasswordsTest(BaseJobTestMixin, django.test.TransactionTestCase):
    def setUp(self):
        super(JobTemplateLaunchPasswordsTest, self).setUp()

        self.url = reverse('api:job_template_list')
        self.data = dict(
            name         = 'launched job template',
            job_type     = PERM_INVENTORY_DEPLOY,
            inventory    = self.inv_eng.pk,
            project      = self.proj_dev.pk,
            credential   = self.cred_sue_ask.pk,
            playbook     = self.proj_dev.playbooks[0],
            ask_credential_on_launch = True,
        )

        with self.current_user(self.user_sue):
            response = self.post(self.url, self.data, expect=201)
            self.launch_url = reverse('api:job_template_launch',
                                      args=(response['id'],))

    # should return explicit credentials required passwords
    def test_explicit_cred_with_ask_passwords_fail(self):
        passwords_required = ['ssh_password', 'become_password', 'ssh_key_unlock']
        # Job Templates with deleted credentials cannot be launched.
        with self.current_user(self.user_sue):
            self.cred_sue_ask.delete()
            response = self.post(self.launch_url, {'credential_id': self.cred_sue_ask_many.pk}, expect=400)
            for p in passwords_required:
                self.assertIn(p, response['passwords_needed_to_start'])
            self.assertEqual(len(passwords_required), len(response['passwords_needed_to_start']))

    def test_explicit_cred_with_ask_password(self):
        with self.current_user(self.user_sue):
            response = self.post(self.launch_url, {'ssh_password': 'whatever'}, expect=201)
            j = Job.objects.get(pk=response['job'])
            self.assertEqual(j.status, 'new')

    def test_explicit_cred_with_ask_password_empty_string_fail(self):
        with self.current_user(self.user_sue):
            response = self.post(self.launch_url, {'ssh_password': ''}, expect=400)
            self.assertIn('ssh_password', response['passwords_needed_to_start'])
