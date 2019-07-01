from koji_wrapper.tag import KojiTag


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


def getRecordForBuild(koji_wrapper, build_id_or_nvr, grab_build_task_info=False):
    builddata = koji_wrapper.session.getBuild(build_id_or_nvr)
    parent_build_id = builddata['extra']['image']['parent_build_id']

    # Useful information but does not include floating tags
    # pullspecs = builddata['extra']['image']['index']['pull']
    # tags = builddata['extra']['image']['index']['tags']
    build_task_id = builddata['extra']['container_koji_task_id']
    task_results = koji_wrapper.session.getTaskResult(build_task_id)
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
        'parent_build_id': parent_build_id
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
