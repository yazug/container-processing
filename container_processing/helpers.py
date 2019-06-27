from koji_wrapper.tag import KojiTag


def get_tags_from_build(koji_session, nvr):
    builddata = koji_session.build(nvr)
    return builddata['extra']['image']['index']['tags']


def get_parent_nvrs(koji_session, nvr):
    builddata = koji_session.session.getBuild(nvr)
    return [i['nvr'] for i in builddata['extra']['image']['partent_image_builds']['tags'].values()]


# Search for batch for a tag (will not pick up isolated builds)
def get_matching_batch_from_tag(osp, batch, rhel, latest=False, koji_session=None, sub_tag='candidate'):
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

        nvr = build['nvr']
        component = build['package_name']
        builddata = koji_tag.session.getBuild(build['id'])
        tags = builddata['extra']['image']['index']['tags']
        if [i for i in tags if batch in i]:
            if component not in matching_containers:
                matching_containers[component] = []
            matching_containers[component].append(nvr)

    return matching_containers


def get_latest_cdn_containers(osp, rhel, koji_session=None):
    tag = "rhos-{0}-rhel-{1}-container-released".format(float(osp), int(rhel))
    if koji_session:
        koji_tag = KojiTag(session=koji_session, tag=tag)
    else:
        koji_tag = KojiTag(profile='brew', tag=tag)

    koji_tag.builds(latest=True, type='image', inherit=False)

    return get_latest_from_koji_tag(koji_tag)


def get_latest_from_koji_tag(koji_tag):
    matching_containers = {}

    for build in koji_tag.builds():
        nvr = build['nvr']
        component = build['package_name']

        if component not in matching_containers:
            matching_containers[component] = []
        matching_containers[component].append(nvr)

    return matching_containers


