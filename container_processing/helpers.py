import pickle
from koji_wrapper.tag import KojiTag
from koji_wrapper.base import KojiWrapperBase
from cachetools import LRUCache
from cachetools import TTLCache
import os.path
import os

CACHE_PATH = "~/.cache/container-processing"
_build_id_to_parent_id = LRUCache(maxsize=16000)
_build_id_to_build_task_id = LRUCache(maxsize=16000)
_build_id_or_nvr_to_build_id = LRUCache(maxsize=16000)
_build_data = TTLCache(maxsize=6000, ttl=604800)
_task_results = TTLCache(maxsize=8000, ttl=604800)

def load_cache():
    global _build_id_to_parent_id
    global _build_id_to_build_task_id
    global _build_data
    global _task_results
    cache_path = os.path.expanduser(CACHE_PATH)

    cache_in = None
    filename = os.path.join(cache_path, 'build_id_to_parent_id')
    if os.path.exists(filename):
        with open(filename, 'rb') as fin:
            cache_in = pickle.load(fin)
    if cache_in is not None:
        _build_id_to_parent_id = cache_in
        print("{0} is now {1}".format(filename, cache_in.currsize))

    cache_in = None
    filename = os.path.join(cache_path, 'build_id_to_build_task_id')
    if os.path.exists(filename):
        with open(filename, 'rb') as fin:
            cache_in = pickle.load(fin)
    if cache_in is not None:
        _build_id_to_build_task_id = cache_in
        print("{0} is now {1}".format(filename, cache_in.currsize))

    cache_in = None
    filename = os.path.join(cache_path, 'build_id_or_nvr_to_build_id')
    if os.path.exists(filename):
        with open(filename, 'rb') as fin:
            cache_in = pickle.load(fin)
    if cache_in is not None:
        _build_id_or_nvr_to_build_id = cache_in
        print("{0} is now {1}".format(filename, cache_in.currsize))

    cache_in = None
    filename = os.path.join(cache_path, 'build_data')
    if os.path.exists(filename):
        with open(filename, 'rb') as fin:
            cache_in = pickle.load(fin)
    if cache_in is not None:
        _build_data = cache_in
        print("{0} is now {1}".format(filename, cache_in.currsize))

    cache_in = None
    filename = os.path.join(cache_path, 'task_results')
    if os.path.exists(filename):
        with open(filename, 'rb') as fin:
            cache_in = pickle.load(fin)
    if cache_in is not None:
        _task_results = cache_in
        print("{0} is now {1}".format(filename, cache_in.currsize))

    _cache_cross_populate()


def _cache_cross_populate():
    for key in _build_data:
        val = _build_data[key]
        if val['nvr'] not in _build_id_or_nvr_to_build_id:
            _build_id_or_nvr_to_build_id[val['nvr']] = key

        _build_id_to_build_task_id[key] = val['extra']['container_koji_task_id']

        if key not in _build_id_to_parent_id:
            _build_id_to_parent_id[key] = val['extra']['image']['parent_build_id']

    for key in _task_results:
        if 'repositories' in _task_results[key] and 'koji_builds' in _task_results[key]:
            for build_id in _task_results[key]['koji_builds']:
                if int(build_id) not in _build_id_to_build_task_id:
                    _build_id_to_build_task_id[int(build_id)] = key


def save_cache():
    cache_path = os.path.expanduser(CACHE_PATH)
    if not os.path.isdir(cache_path):
        os.makedirs(cache_path)

    for filename, cache in [('build_id_to_parent_id', _build_id_to_parent_id),
                            ('build_id_to_build_task_id', _build_id_to_build_task_id),
                            ('build_data', _build_data),
                            ('task_results', _task_results),
                            ('build_id_or_nvr_to_build_id', _build_id_or_nvr_to_build_id)]:
        with open(os.path.join(cache_path, filename), 'wb') as fout:
            pickle.dump(cache, fout)
            print("{0} is now {1}".format(filename, cache.currsize))


# Search for batch for a tag (will not pick up isolated builds)
def get_matching_batch_from_tag(osp, rhel, batch, latest=False, koji_session=None, sub_tag='candidate'):
    tag = "rhos-{0}-rhel-{1}-{2}".format(float(osp), int(rhel), sub_tag)
    if koji_session:
        koji_tag = KojiTag(session=koji_session, tag=tag)
    else:
        koji_tag = KojiTag(profile='brew', tag=tag)

    koji_tag.builds(latest=latest, type='image', inherit=False)

    return get_matching_batch_from_koji_tag(koji_tag, batch)


def get_matching_batch_from_koji_tag(koji_tag, batch):

    matching_containers = {}
    for build in koji_tag.builds():
        if '-container' not in build['package_name']:
            continue

        record = getRecordForBuild(koji_tag, build['id'], grab_build_task_info=True)
        component = record['package_name']

        if [i for i in record['task_pullspecs'] if batch in i]:
            if component not in matching_containers:
                matching_containers[component] = []
            matching_containers[component].append(record)

    return matching_containers


def get_latest_cdn_containers(osp, rhel, koji_session=None, latest=True, extra_info=False):
    tag = "rhos-{0}-rhel-{1}-container-released".format(float(osp), int(rhel))
    if koji_session:
        koji_tag = KojiTag(session=koji_session, tag=tag)
    else:
        koji_tag = KojiTag(profile='brew', tag=tag)

    koji_tag.builds(latest=latest, type='image', inherit=False)

    return get_container_builds_from_koji_tag(koji_tag, get_extra_info=extra_info)

def getBuildId(build_id_or_nvr, koji_session=None):
    global _build_data
    global _build_id_or_nvr_to_build_id

    build_id = None
    if build_id_or_nvr in _build_data:
        build_id = build_id_or_nvr

    if build_id is None and build_id_or_nvr in _build_id_or_nvr_to_build_id:
        build_id = _build_id_or_nvr_to_build_id[build_id_or_nvr]

    if build_id is None and koji_session:
        build_id = getBuildData(build_id_or_nvr, koji_session)['id']

    return build_id


def getBuildData(build_id_or_nvr, koji_session=None):
    global _build_data
    global _build_id_to_parent_id
    global _build_id_to_build_task_id
    global _build_id_or_nvr_to_build_id

    build_id = getBuildId(build_id_or_nvr)

    if (build_id is None or build_id not in _build_data) and koji_session is not None:
        builddata = koji_session.session.getBuild(build_id_or_nvr)
        build_id = builddata['id']

        _build_data[build_id] = builddata
        _build_id_or_nvr_to_build_id[builddata['nvr']] = builddata['id']
        _build_id_to_parent_id[build_id] = builddata['extra']['image']['parent_build_id']
        _build_id_to_build_task_id[build_id] = builddata['extra']['container_koji_task_id']

    return _build_data[build_id]


def getTaskResults(task_id, koji_session=None):
    global _task_results

    if task_id not in _task_results and koji_session is not None:
        _task_results[task_id] = koji_session.session.getTaskResult(task_id)

    return _task_results[task_id]


def getBuildTaskId(build_id, koji_session=None):
    if build_id not in _build_id_to_build_task_id:
        getBuildData(build_id, koji_session=koji_session)

    return _build_id_to_build_task_id[build_id]


def getRecordForBuild(koji_wrapper, build_id_or_nvr, grab_build_task_info=False):
    global _build_id_to_parent_id
    global _build_id_or_nvr_to_build_id

    build_id = getBuildId(build_id_or_nvr, koji_session=koji_wrapper)
    builddata = getBuildData(build_id, koji_session=koji_wrapper)

    # Useful information but does not include floating tags
    # pullspecs = builddata['extra']['image']['index']['pull']
    # tags = builddata['extra']['image']['index']['tags']
    #build_task_id = builddata['extra']['container_koji_task_id']

    build_task_id = getBuildTaskId(build_id, koji_session=koji_wrapper)
    task_results = getTaskResults(build_task_id, koji_wrapper)

    if build_task_id not in _task_results:
        _task_results[build_task_id] = koji_wrapper.session.getTaskResult(build_task_id)

    task_results = _task_results[build_task_id]
    pullspecs = task_results['repositories']

    # tags from builddata will be only non floating tags
    # pullsepcs from builddata will only be main :{ver}-{rel}
    return {
        'package_name': builddata['package_name'],
        'nvr': builddata['nvr'],
        'build_id': builddata['id'],
        'build_pullspecs': builddata['extra']['image']['index']['pull'],
        'build_tags': builddata['extra']['image']['index']['tags'],
        'task_pullspecs': pullspecs,
        'parent_build_id': _build_id_to_parent_id[build_id]
    }


def get_container_builds_from_koji_tag(koji_tag, get_extra_info=False):
    matching_containers = {}

    for build in koji_tag.builds():
        component = build['package_name']

        if component not in matching_containers:
            matching_containers[component] = []

        record = getRecordForBuild(koji_tag, build['id'], grab_build_task_info=False)
        matching_containers[component].append(record)

    return matching_containers
