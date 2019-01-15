from unittest import mock
from unittest.mock import call

from kubernetes.client.rest import ApiException
from nephos.fabric.ca import (ca_chart,
                              ca_enroll, check_ca, ca_secrets, setup_ca)


class TestCaChart:
    @mock.patch('nephos.fabric.ca.secret_read')
    @mock.patch('nephos.fabric.ca.helm_upgrade')
    @mock.patch('nephos.fabric.ca.helm_install')
    def test_ca_chart(self, mock_helm_install, mock_helm_upgrade, mock_secret_read):
        mock_secret_read.side_effect = [{'postgresql-password': 'a_password'}]
        opts = {'core': {'dir_values': './some_dir', 'chart_repo': 'a_repo', 'namespace': 'a-namespace'}}
        env_vars = [('externalDatabase.password', 'a_password')]
        ca_chart(opts, 'a-release')
        mock_helm_install.assert_has_calls([
            call('stable', 'postgresql', 'a-release-pg', 'a-namespace',
                 config_yaml='./some_dir/postgres-ca/a-release-pg.yaml', verbose=False),
            call('a_repo', 'hlf-ca', 'a-release', 'a-namespace',
                 config_yaml='./some_dir/hlf-ca/a-release.yaml', env_vars=env_vars, verbose=False)
        ])
        mock_helm_upgrade.assert_not_called()
        mock_secret_read.assert_called_once_with(
            'a-release-pg-postgresql', 'a-namespace', verbose=False)

    @mock.patch('nephos.fabric.ca.secret_read')
    @mock.patch('nephos.fabric.ca.helm_upgrade')
    @mock.patch('nephos.fabric.ca.helm_install')
    def test_ca_chart_upgrade(self, mock_helm_install, mock_helm_upgrade, mock_secret_read):
        mock_secret_read.side_effect = [{'postgresql-password': 'a_password'}]
        opts = {'core': {'dir_values': './some_dir', 'chart_repo': 'a_repo', 'namespace': 'a-namespace'}}
        env_vars = [('externalDatabase.password', 'a_password')]
        preserve = (('a-release-hlf-ca', 'CA_ADMIN', 'adminUsername'),
                    ('a-release-hlf-ca', 'CA_PASSWORD', 'adminPassword'))
        ca_chart(opts, 'a-release', upgrade=True)
        mock_helm_install.assert_called_once_with(
            'stable', 'postgresql', 'a-release-pg', 'a-namespace',
            config_yaml='./some_dir/postgres-ca/a-release-pg.yaml', verbose=False)
        mock_helm_upgrade.assert_called_once_with(
            'a_repo', 'hlf-ca', 'a-release', 'a-namespace',
            config_yaml='./some_dir/hlf-ca/a-release.yaml',
            env_vars=env_vars, preserve=preserve, verbose=False
        )
        mock_secret_read.assert_called_once_with(
            'a-release-pg-postgresql', 'a-namespace', verbose=False)

    @mock.patch('nephos.fabric.ca.secret_read')
    @mock.patch('nephos.fabric.ca.helm_upgrade')
    @mock.patch('nephos.fabric.ca.helm_install')
    def test_ca_chart_verbose(self, mock_helm_install, mock_helm_upgrade, mock_secret_read):
        mock_secret_read.side_effect = [{'postgresql-password': 'a_password'}]
        opts = {'core': {'dir_values': './some_dir', 'chart_repo': 'a_repo', 'namespace': 'a-namespace'}}
        env_vars = [('externalDatabase.password', 'a_password')]
        ca_chart(opts, 'a-release', verbose=True)
        mock_helm_install.assert_has_calls([
            call('stable', 'postgresql', 'a-release-pg', 'a-namespace',
                 config_yaml='./some_dir/postgres-ca/a-release-pg.yaml', verbose=True),
            call('a_repo', 'hlf-ca', 'a-release', 'a-namespace',
                 config_yaml='./some_dir/hlf-ca/a-release.yaml', env_vars=env_vars, verbose=True)
        ])
        mock_helm_upgrade.assert_not_called()
        mock_secret_read.assert_called_once_with(
            'a-release-pg-postgresql', 'a-namespace', verbose=True)


class TestCaEnroll:
    @mock.patch('nephos.fabric.ca.sleep')
    def test_ca_enroll(self, mock_sleep):
        mock_pod_exec = mock.Mock()
        mock_pod_exec.execute.side_effect = [
            None,  # Get CA cert
            'enrollment'
        ]
        mock_pod_exec.logs.side_effect = [
            'Not yet running',
            'Not yet running\nListening on localhost:7050'
        ]
        ca_enroll(mock_pod_exec)
        mock_pod_exec.execute.assert_has_calls([
            call('cat /var/hyperledger/fabric-ca/msp/signcerts/cert.pem'),
            call("bash -c 'fabric-ca-client enroll -d -u http://$CA_ADMIN:$CA_PASSWORD@$SERVICE_DNS:7054'")
        ])
        assert mock_pod_exec.logs.call_count == 2
        mock_sleep.assert_called_once_with(15)

    @mock.patch('nephos.fabric.ca.sleep')
    def test_ca_enroll_again(self, mock_sleep):
        mock_pod_exec = mock.Mock()
        mock_pod_exec.execute.side_effect = [
            'ca-cert',  # Get CA cert
        ]
        mock_pod_exec.logs.side_effect = [
            'Not yet running\nListening on localhost:7050'
        ]
        ca_enroll(mock_pod_exec)
        mock_pod_exec.execute.assert_called_once_with('cat /var/hyperledger/fabric-ca/msp/signcerts/cert.pem')
        assert mock_pod_exec.logs.call_count == 1
        mock_sleep.assert_not_called()


class CheckCa:
    @mock.patch('nephos.fabric.ca.execute_until_success')
    def test_check_ca(self, mock_execute_until_success):
        check_ca('an-ingress', verbose=False)
        mock_execute_until_success.assert_called_once_with('curl https://an-ingress/cainfo', verbose=False)

    @mock.patch('nephos.fabric.ca.execute_until_success')
    def test_check_ca_verbose(self, mock_execute_until_success):
        check_ca('an-ingress', verbose=True)
        mock_execute_until_success.assert_called_once_with('curl https://an-ingress/cainfo', verbose=True)


class TestCaSecrets:
    @mock.patch('nephos.fabric.ca.shutil')
    @mock.patch('nephos.fabric.ca.secret_from_file')
    @mock.patch('nephos.fabric.ca.makedirs')
    @mock.patch('nephos.fabric.ca.glob')
    def test_ca_secrets(self, mock_glob, mock_makedirs, mock_secret_from_file, mock_shutil):
        ADMIN_CERT = './a_dir/a_MSP/admincerts/cert.pem'
        ADMIN_KEY = './a_dir/a_MSP/keystore/secret_sk'
        mock_glob.glob.side_effect = [[ADMIN_KEY]]
        ca_values = {'msp': 'a_MSP', 'org_admincert': 'a-secret-cert', 'org_adminkey': 'a-secret-key'}
        ca_secrets(ca_values, 'a-namespace', './a_dir')
        mock_makedirs.assert_called_once_with('./a_dir/a_MSP/admincerts')
        mock_shutil.copy.assert_called_once_with('./a_dir/a_MSP/signcerts/cert.pem', './a_dir/a_MSP/admincerts/cert.pem')
        mock_glob.glob.assert_called_once_with('./a_dir/a_MSP/keystore/*_sk')
        mock_secret_from_file.assert_has_calls([
            call(secret='a-secret-cert', namespace='a-namespace', key='cert.pem', filename=ADMIN_CERT,
                     verbose=False),
            call(secret='a-secret-key', namespace='a-namespace', key='key.pem', filename=ADMIN_KEY,
                     verbose=False)
        ])


class TestSetupCa:
    root_executer = mock.Mock()
    root_executer.pod = 'root-pod'
    int_executer = mock.Mock()
    int_executer.pod = 'int-pod'

    @mock.patch('nephos.fabric.ca.ingress_read')
    @mock.patch('nephos.fabric.ca.get_pod')
    @mock.patch('nephos.fabric.ca.check_ca')
    @mock.patch('nephos.fabric.ca.ca_enroll')
    @mock.patch('nephos.fabric.ca.ca_chart')
    def test_setup_ca(self, mock_ca_chart, mock_ca_enroll,
                mock_check_ca, mock_get_pod, mock_ingress_read):
        mock_get_pod.side_effect = [self.root_executer, self.int_executer]
        mock_ingress_read.side_effect = [ApiException, ['an-ingress']]
        OPTS = {
            'core': {'namespace': 'a-namespace', 'dir_config': './a_dir'},
            'cas': {'root-ca': 'ca-values', 'int-ca': 'other-values'}
            }
        setup_ca(OPTS)
        mock_ca_chart.assert_has_calls([
            call(opts=OPTS, release='root-ca', upgrade=False, verbose=False),
            call(opts=OPTS, release='int-ca', upgrade=False, verbose=False),
        ])
        mock_get_pod.assert_has_calls([
            call(namespace='a-namespace', release='root-ca', app='hlf-ca', verbose=False),
            call(namespace='a-namespace', release='int-ca', app='hlf-ca', verbose=False)
        ])
        mock_ca_enroll.assert_has_calls([
            call(self.root_executer),
            call(self.int_executer),
            ])
        mock_ingress_read.assert_has_calls([
            call('root-ca-hlf-ca', namespace='a-namespace', verbose=False),
            call('int-ca-hlf-ca', namespace='a-namespace', verbose=False)
        ])
        mock_check_ca.assert_called_once_with(ingress_host='an-ingress', verbose=False)

    @mock.patch('nephos.fabric.ca.ingress_read')
    @mock.patch('nephos.fabric.ca.get_pod')
    @mock.patch('nephos.fabric.ca.check_ca')
    @mock.patch('nephos.fabric.ca.ca_enroll')
    @mock.patch('nephos.fabric.ca.ca_chart')
    def test_setup_ca_upgrade(self, mock_ca_chart, mock_ca_enroll,
                        mock_check_ca, mock_get_pod, mock_ingress_read):
        mock_get_pod.side_effect = [self.root_executer, self.int_executer]
        mock_ingress_read.side_effect =[ApiException]
        OPTS = {
            'core': {'namespace': 'a-namespace', 'dir_config': './a_dir'},
            'cas': {'root-ca': 'ca-values'}
            }
        setup_ca(OPTS, upgrade=True, verbose=True)
        mock_ca_chart.assert_called_once_with(opts=OPTS, release='root-ca', upgrade=True, verbose=True)
        mock_get_pod.assert_called_once_with(namespace='a-namespace', release='root-ca', app='hlf-ca', verbose=True)
        mock_ca_enroll.assert_called_once_with(self.root_executer)
        mock_ingress_read.assert_called_once_with('root-ca-hlf-ca', namespace='a-namespace', verbose=True)
        mock_check_ca.assert_not_called()
