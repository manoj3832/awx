# Copyright (c) 2015 Ansible, Inc.
# All Rights Reserved.

# Python
import json
import os
import subprocess
import sys
import urlparse

# AWX
from awx.main.models import * # noqa
from awx.main.tests.base import BaseLiveServerTest

__all__ = ['InventoryScriptTest']


class BaseScriptTest(BaseLiveServerTest):
    '''
    Base class for tests that run external scripts to access the API.
    '''

    def setUp(self):
        super(BaseScriptTest, self).setUp()
        self._sys_path = [x for x in sys.path]
        self._environ = dict(os.environ.items())
        self._temp_files = []

    def tearDown(self):
        super(BaseScriptTest, self).tearDown()
        sys.path = self._sys_path
        for k,v in self._environ.items():
            if os.environ.get(k, None) != v:
                os.environ[k] = v
        for k,v in os.environ.items():
            if k not in self._environ.keys():
                del os.environ[k]
        for tf in self._temp_files:
            if os.path.exists(tf):
                os.remove(tf)

    def run_script(self, name, *args, **options):
        '''
        Run an external script and capture its stdout/stderr and return code.
        '''
        #stdin_fileobj = options.pop('stdin_fileobj', None)
        pargs = [name]
        for k,v in options.items():
            pargs.append('%s%s' % ('-' if len(k) == 1 else '--', k))
            if v is not True:
                pargs.append(str(v))
        for arg in args:
            pargs.append(str(arg))
        proc = subprocess.Popen(pargs, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        return proc.returncode, stdout, stderr


class InventoryScriptTest(BaseScriptTest):
    '''
    Test helper to run management command as standalone script.
    '''

    def setUp(self):
        super(InventoryScriptTest, self).setUp()
        self.start_rabbit()
        self.setup_instances()
        self.setup_users()
        self.organizations = self.make_organizations(self.super_django_user, 2)
        self.projects = self.make_projects(self.normal_django_user, 2)
        self.organizations[0].projects.add(self.projects[1])
        self.organizations[1].projects.add(self.projects[0])
        self.inventories = []
        self.hosts = []
        self.groups = []
        for n, organization in enumerate(self.organizations):
            inventory = Inventory.objects.create(name='inventory-%d' % n,
                                                 description='description for inventory %d' % n,
                                                 organization=organization,
                                                 variables=json.dumps({'n': n}) if n else '')
            self.inventories.append(inventory)
            hosts = []
            for x in xrange(10):
                if n > 0:
                    variables = json.dumps({'ho': 'hum-%d' % x})
                else:
                    variables = ''
                host = inventory.hosts.create(name='host-%02d-%02d.example.com' % (n, x),
                                              inventory=inventory,
                                              variables=variables)
                #if x in (3, 7):
                #    host.delete()
                #    continue
                hosts.append(host)


            # add localhost just to make sure it's thrown into all (Ansible github bug)
            local = inventory.hosts.create(name='localhost', inventory=inventory, variables={})
            hosts.append(local)

            self.hosts.extend(hosts)
            groups = []
            for x in xrange(5):
                if n > 0:
                    variables = json.dumps({'gee': 'whiz-%d' % x})
                else:
                    variables = ''
                group = inventory.groups.create(name='group-%d' % x,
                                                inventory=inventory,
                                                variables=variables)
                #if x == 2:
                #    #group.delete()
                #    #continue
                groups.append(group)
                group.hosts.add(hosts[x])
                group.hosts.add(hosts[x + 5])
                if n > 0 and x == 4:
                    group.parents.add(groups[3])
                if x == 4:
                    group.hosts.add(local)
            self.groups.extend(groups)

            hosts[3].delete()
            hosts[7].delete()
            groups[2].delete()




    def tearDown(self):
        super(InventoryScriptTest, self).tearDown()
        self.stop_rabbit()

    def run_inventory_script(self, *args, **options):
        rest_api_url = self.live_server_url
        parts = urlparse.urlsplit(rest_api_url)
        username, password = self.get_super_credentials()
        netloc = '%s:%s@%s' % (username, password, parts.netloc)
        rest_api_url = urlparse.urlunsplit([parts.scheme, netloc, parts.path,
                                            parts.query, parts.fragment])
        os.environ.setdefault('REST_API_URL', rest_api_url)
        #os.environ.setdefault('REST_API_TOKEN',
        #                      self.super_django_user.auth_token.key)
        name = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'plugins',
                            'inventory', 'awxrest.py')
        return self.run_script(name, *args, **options)

    def test_without_inventory_id(self):
        rc, stdout, stderr = self.run_inventory_script(list=True)
        self.assertNotEqual(rc, 0, stderr)
        self.assertEqual(json.loads(stdout), {'failed': True})
        rc, stdout, stderr = self.run_inventory_script(host=self.hosts[0].name)
        self.assertNotEqual(rc, 0, stderr)
        self.assertEqual(json.loads(stdout), {'failed': True})

    def test_list_with_inventory_id_as_argument(self):
        inventory = self.inventories[0]
        rc, stdout, stderr = self.run_inventory_script(list=True,
                                                       inventory=inventory.pk)
        self.assertEqual(rc, 0, stderr)
        data = json.loads(stdout)
        groups = inventory.groups
        groupnames = [ x for x in groups.values_list('name', flat=True)]

        # it's ok for all to be here because due to an Ansible inventory workaround
        # 127.0.0.1/localhost must show up in the all group
        groupnames.append('all')
        self.assertEqual(set(data.keys()), set(groupnames))

        # Groups for this inventory should only have hosts, and no group
        # variable data or parent/child relationships.
        for k,v in data.items():
            if k != 'all':
                assert isinstance(v, dict)
                assert isinstance(v['children'], (list,tuple))
                assert isinstance(v['hosts'], (list,tuple))
                assert isinstance(v['vars'], (dict))
                group = inventory.groups.get(name=k)
                hosts = group.hosts
                hostnames = hosts.values_list('name', flat=True)
                self.assertEqual(set(v['hosts']), set(hostnames))
            else:
                assert v['hosts'] == ['host-00-02.example.com', 'localhost']

        # Command line argument for inventory ID should take precedence over
        # environment variable.
        inventory_pks = set(map(lambda x: x.pk, self.inventories))
        invalid_id = [x for x in xrange(9999) if x not in inventory_pks][0]
        os.environ['INVENTORY_ID'] = str(invalid_id)
        rc, stdout, stderr = self.run_inventory_script(list=True,
                                                       inventory=inventory.pk)
        self.assertEqual(rc, 0, stderr)
        data = json.loads(stdout)

    def test_list_with_inventory_id_in_environment(self):
        inventory = self.inventories[1]
        os.environ['INVENTORY_ID'] = str(inventory.pk)
        rc, stdout, stderr = self.run_inventory_script(list=True)
        self.assertEqual(rc, 0, stderr)
        data = json.loads(stdout)
        groups = inventory.groups
        groupnames = list(groups.values_list('name', flat=True)) + ['all']
        self.assertEqual(set(data.keys()), set(groupnames))
        # Groups for this inventory should have hosts, variable data, and one
        # parent/child relationship.
        for k,v in data.items():
            assert isinstance(v, dict)
            if k == 'all':
                self.assertEqual(v.get('vars', {}), inventory.variables_dict)
                continue
            group = inventory.groups.get(name=k)
            hosts = group.hosts
            hostnames = hosts.values_list('name', flat=True)
            self.assertEqual(set(v.get('hosts', [])), set(hostnames))
            if group.variables:
                self.assertEqual(v.get('vars', {}), group.variables_dict)
            if k == 'group-3':
                children = group.children
                childnames = children.values_list('name', flat=True)
                self.assertEqual(set(v.get('children', [])), set(childnames))
            else:
                assert len(v['children']) == 0

    def test_list_with_hostvars_inline(self):
        inventory = self.inventories[1]
        rc, stdout, stderr = self.run_inventory_script(list=True,
                                                       inventory=inventory.pk,
                                                       hostvars=True)
        self.assertEqual(rc, 0, stderr)
        data = json.loads(stdout)
        groups = inventory.groups
        groupnames = list(groups.values_list('name', flat=True))
        groupnames.extend(['all', '_meta'])
        self.assertEqual(set(data.keys()), set(groupnames))
        all_hostnames = set()
        # Groups for this inventory should have hosts, variable data, and one
        # parent/child relationship.
        for k,v in data.items():
            assert isinstance(v, dict)
            if k == 'all':
                self.assertEqual(v.get('vars', {}), inventory.variables_dict)
                continue
            if k == '_meta':
                continue
            group = inventory.groups.get(name=k)
            hosts = group.hosts
            hostnames = hosts.values_list('name', flat=True)
            all_hostnames.update(hostnames)
            assert set(v.get('hosts', [])) == set(hostnames)
            if group.variables:
                assert v.get('vars', {}) == group.variables_dict
            if k == 'group-3':
                children = group.children
                childnames = children.values_list('name', flat=True)
                assert set(v.get('children', [])) == set(childnames)
            else:
                assert len(v['children']) == 0
        # Check hostvars in ['_meta']['hostvars'] dict.
        for hostname in all_hostnames:
            assert hostname in data['_meta']['hostvars']
            host = inventory.hosts.get(name=hostname)
            self.assertEqual(data['_meta']['hostvars'][hostname],
                             host.variables_dict)
        # Hostvars can also be requested via environment variable.
        os.environ['INVENTORY_HOSTVARS'] = str(True)
        rc, stdout, stderr = self.run_inventory_script(list=True,
                                                       inventory=inventory.pk)
        self.assertEqual(rc, 0, stderr)
        data = json.loads(stdout)
        assert '_meta' in data

    def test_valid_host(self):
        # Host without variable data.
        inventory = self.inventories[0]
        host = inventory.hosts.all()[2]
        os.environ['INVENTORY_ID'] = str(inventory.pk)
        rc, stdout, stderr = self.run_inventory_script(host=host.name)
        self.assertEqual(rc, 0, stderr)
        data = json.loads(stdout)
        self.assertEqual(data, {})
        # Host with variable data.
        inventory = self.inventories[1]
        host = inventory.hosts.all()[4]
        os.environ['INVENTORY_ID'] = str(inventory.pk)
        rc, stdout, stderr = self.run_inventory_script(host=host.name)
        self.assertEqual(rc, 0, stderr)
        data = json.loads(stdout)
        self.assertEqual(data, host.variables_dict)

    def test_invalid_host(self):
        # Valid host, but not part of the specified inventory.
        inventory = self.inventories[0]
        host = Host.objects.exclude(inventory=inventory)[0]
        os.environ['INVENTORY_ID'] = str(inventory.pk)
        rc, stdout, stderr = self.run_inventory_script(host=host.name)
        self.assertNotEqual(rc, 0, stderr)
        self.assertEqual(json.loads(stdout), {'failed': True})
        # Invalid hostname not in database.
        rc, stdout, stderr = self.run_inventory_script(host='blah.example.com')
        self.assertNotEqual(rc, 0, stderr)
        self.assertEqual(json.loads(stdout), {'failed': True})

    def test_with_invalid_inventory_id(self):
        inventory_pks = set(map(lambda x: x.pk, self.inventories))
        invalid_id = [x for x in xrange(1, 9999) if x not in inventory_pks][0]
        os.environ['INVENTORY_ID'] = str(invalid_id)
        rc, stdout, stderr = self.run_inventory_script(list=True)
        self.assertNotEqual(rc, 0, stderr)
        self.assertEqual(json.loads(stdout), {'failed': True})
        os.environ['INVENTORY_ID'] = 'not_an_int'
        rc, stdout, stderr = self.run_inventory_script(list=True)
        self.assertNotEqual(rc, 0, stderr)
        self.assertEqual(json.loads(stdout), {'failed': True})
        os.environ['INVENTORY_ID'] = str(invalid_id)
        rc, stdout, stderr = self.run_inventory_script(host=self.hosts[1].name)
        self.assertNotEqual(rc, 0, stderr)
        self.assertEqual(json.loads(stdout), {'failed': True})
        os.environ['INVENTORY_ID'] = 'not_an_int'
        rc, stdout, stderr = self.run_inventory_script(host=self.hosts[2].name)
        self.assertNotEqual(rc, 0, stderr)
        self.assertEqual(json.loads(stdout), {'failed': True})

    def test_with_deleted_inventory(self):
        inventory = self.inventories[0]
        pk = inventory.pk
        inventory.delete()
        os.environ['INVENTORY_ID'] = str(pk)
        rc, stdout, stderr = self.run_inventory_script(list=True)
        self.assertNotEqual(rc, 0, stderr)
        self.assertEqual(json.loads(stdout), {'failed': True})

    def test_without_list_or_host_argument(self):
        inventory = self.inventories[0]
        os.environ['INVENTORY_ID'] = str(inventory.pk)
        rc, stdout, stderr = self.run_inventory_script()
        self.assertNotEqual(rc, 0, stderr)
        self.assertEqual(json.loads(stdout), {'failed': True})

    def test_with_both_list_and_host_arguments(self):
        inventory = self.inventories[0]
        os.environ['INVENTORY_ID'] = str(inventory.pk)
        rc, stdout, stderr = self.run_inventory_script(list=True, host='blah')
        self.assertNotEqual(rc, 0, stderr)
        self.assertEqual(json.loads(stdout), {'failed': True})

    def test_with_disabled_hosts(self):
        inventory = self.inventories[1]
        for host in inventory.hosts.filter(enabled=True):
            host.enabled = False
            host.save(update_fields=['enabled'])
        os.environ['INVENTORY_ID'] = str(inventory.pk)
        # Load inventory list as normal (only enabled hosts).
        rc, stdout, stderr = self.run_inventory_script(list=True)
        self.assertEqual(rc, 0, stderr)
        data = json.loads(stdout)
        groups = inventory.groups
        groupnames = list(groups.values_list('name', flat=True)) + ['all']
        self.assertEqual(set(data.keys()), set(groupnames))
        for k,v in data.items():
            assert isinstance(v, dict)
            if k == 'all':
                self.assertEqual(v.get('vars', {}), inventory.variables_dict)
                continue
            group = inventory.groups.get(name=k)
            hosts = group.hosts.filter(enabled=True)
            hostnames = hosts.values_list('name', flat=True)
            self.assertEqual(set(v.get('hosts', [])), set(hostnames))
            self.assertFalse(hostnames)
            if group.variables:
                self.assertEqual(v.get('vars', {}), group.variables_dict)
            if k == 'group-3':
                children = group.children
                childnames = children.values_list('name', flat=True)
                self.assertEqual(set(v.get('children', [])), set(childnames))
            else:
                assert len(v['children']) == 0
        # Load inventory list with all hosts.
        rc, stdout, stderr = self.run_inventory_script(list=True, all=True)
        self.assertEqual(rc, 0, stderr)
        data = json.loads(stdout)
        groups = inventory.groups
        groupnames = list(groups.values_list('name', flat=True)) + ['all']
        self.assertEqual(set(data.keys()), set(groupnames))
        for k,v in data.items():
            assert isinstance(v, dict)
            if k == 'all':
                self.assertEqual(v.get('vars', {}), inventory.variables_dict)
                continue
            group = inventory.groups.get(name=k)
            hosts = group.hosts
            hostnames = hosts.values_list('name', flat=True)
            self.assertEqual(set(v.get('hosts', [])), set(hostnames))
            assert hostnames
            if group.variables:
                self.assertEqual(v.get('vars', {}), group.variables_dict)
            if k == 'group-3':
                children = group.children
                childnames = children.values_list('name', flat=True)
                self.assertEqual(set(v.get('children', [])), set(childnames))
            else:
                assert len(v['children']) == 0
