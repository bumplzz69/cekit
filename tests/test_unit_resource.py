import pytest
import os
import yaml

from cekit.descriptor import Resource, Image, Overrides
from cekit.config import Config
from cekit.errors import CekitError

config = Config()

def setup_function(function):
    config.cfg['common'] = {'work_dir': '/tmp'}

    if os.path.exists('file'):
        os.remove('file')


def test_repository_dir_is_constructed_properly(mocker):
    mocker.patch('subprocess.check_output')
    mocker.patch('os.path.isdir', ret='True')
    res = Resource({'git': {'url': 'url/repo', 'ref': 'ref'}})
    assert res.copy('dir') == 'dir/repo-ref'


def test_git_clone(mocker):
    mock = mocker.patch('subprocess.check_output')
    mocker.patch('os.path.isdir', ret='True')
    res = Resource({'git': {'url': 'url', 'ref': 'ref'}})
    res.copy('dir')
    mock.assert_called_with(['git',
                             'clone',
                             '--depth',
                             '1',
                             'url',
                             'dir/url-ref',
                             '-b',
                             'ref'],
                            stderr=-2)


def get_res(mocker):
    res = mocker.Mock()
    res.status_code = 200
    res.iter_content = lambda chunk_size: [b'test']
    return res


def get_ctx(mocker):
    ctx = mocker.Mock()
    ctx.check_hostname = True
    ctx.verify_mode = 1
    return ctx


def get_mock_urlopen(mocker):
    return mocker.patch('cekit.descriptor.resource.urlopen', return_value=get_res(mocker))


def get_mock_ssl(mocker, ctx):
    return mocker.patch('cekit.descriptor.resource.ssl.create_default_context',
                        return_value=ctx)


def test_fetching_with_ssl_verify(mocker):
    config.cfg['common']['ssl_verify'] = True
    ctx = get_ctx(mocker)
    get_mock_ssl(mocker, ctx)
    mock_urlopen = get_mock_urlopen(mocker)

    res = Resource({'name': 'file', 'url': 'https:///dummy'})
    try:
        res.copy()
    except:
        pass

    mock_urlopen.assert_called_with('https:///dummy', context=ctx)
    assert ctx.check_hostname is True
    assert ctx.verify_mode == 1


def test_fetching_disable_ssl_verify(mocker):
    config.cfg['common']['ssl_verify'] = False

    mock_urlopen = get_mock_urlopen(mocker)
    ctx = get_ctx(mocker)
    get_mock_ssl(mocker, ctx)

    res = Resource({'name': 'file', 'url': 'https:///dummy'})
    try:
        res.copy()
    except:
        pass

    mock_urlopen.assert_called_with('https:///dummy', context=ctx)

    assert ctx.check_hostname is False
    assert ctx.verify_mode == 0


def test_fetching_bad_status_code():
    res = Resource(
        {'name': 'file', 'url': 'http:///dummy'})
    with pytest.raises(CekitError):
        res.copy()


def test_fetching_file_exists_but_used_as_is(mocker):
    """
    It should not download the file, because we didn't
    specify any hash algorithm, so integrity checking is
    implicitly disabled here.
    """
    with open('file', 'w') as f:  # noqa: F841
        pass
    mock_urlopen = get_mock_urlopen(mocker)
    res = Resource({'name': 'file',
                    'url': 'http:///dummy',
                    'md5': 'd41d8cd98f00b204e9800998ecf8427e'})
    res.copy()
    mock_urlopen.assert_not_called()


def test_fetching_file_exists_fetched_again(mocker):
    """
    It should download the file again, because available
    file locally doesn't match checksum.
    """
    mock_urlopen = get_mock_urlopen(mocker)
    ctx = get_ctx(mocker)
    get_mock_ssl(mocker, ctx)

    with open('file', 'w') as f:  # noqa: F841
        pass
    res = Resource({'name': 'file', 'url': 'http:///dummy', 'md5': '123456'})
    with pytest.raises(CekitError):
        # Checksum will fail, because the "downloaded" file
        # will not have md5 equal to 123456. We need investigate
        # mocking of requests get calls to do it properly
        res.copy()
    mock_urlopen.assert_called_with('http:///dummy', context=ctx)


def test_fetching_file_exists_no_hash_fetched_again(mocker):
    """
    It should download the file again, because available
    file locally doesn't match checksum.
    """
    mock_urlopen = get_mock_urlopen(mocker)
    ctx = get_ctx(mocker)
    get_mock_ssl(mocker, ctx)

    with open('file', 'w') as f:  # noqa: F841
        pass
    res = Resource({'name': 'file', 'url': 'http:///dummy'})
    with pytest.raises(CekitError):
        # url is not valid so we get error, but we are not interested
        # in it. We just need to check that we attempted to downlad.
        res.copy()
    mock_urlopen.assert_called_with('http:///dummy', context=ctx)


def test_generated_url_without_cacher():
    res = Resource({'url': 'url'})
    assert res._Resource__substitute_cache_url('url') == 'url'


def test_resource_verify(mocker):
    mock = mocker.patch('cekit.descriptor.resource.check_sum')
    res = Resource({'url': 'dummy',
                    'sha256': 'justamocksum'})
    res._Resource__verify('dummy')
    mock.assert_called_with('dummy', 'sha256', 'justamocksum', 'dummy')


def test_generated_url_with_cacher():
    config.cfg['common']['cache_url'] = '#filename#,#algorithm#,#hash#'
    res = Resource({'url': 'dummy',
                    'sha256': 'justamocksum'})
    res.name = 'file'
    assert res._Resource__substitute_cache_url('file') == 'file,sha256,justamocksum'


def test_path_resource_absolute():
    res = Resource({'name': 'foo',
                    'path': '/bar'}, directory='/foo')
    assert res.path == '/bar'


def test_path_resource_relative():
    res = Resource({'name': 'foo',
                    'path': 'bar'}, directory='/foo')
    assert res.path == '/foo/bar'


def test_overide_resource_remove_chksum():
    image = Image(yaml.safe_load("""
    from: foo
    name: test/foo
    version: 1.9
    artifacts:
      - name: abs
        path: /tmp/abs
        md5: 'foo'
        sha1: 'foo'
        sha256: 'foo'
    """), 'foo')
    overrides = Overrides(yaml.safe_load("""
    artifacts:
      - name: abs
        path: /tmp/over
"""), 'foo')
    overrides.merge(image)

    assert overrides['from'] == 'foo'
    assert overrides['artifacts'][0]['path'] == '/tmp/over'
    assert 'md5' not in overrides['artifacts'][0]
    assert 'sha1' not in overrides['artifacts'][0]
    assert 'sha256' not in overrides['artifacts'][0]
