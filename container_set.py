
import argparse
from container_processing.caching_koji import CachingKojiWrapper


def get_options():
    parser = argparse.ArgumentParser()
    parser.add_argument('osp', type=float,
                        help='osp version to work with')
    parser.add_argument('--rhel', default=7, type=str,
                        help='rhel version to work with (should match '
                        'rhos-XX-rhel-<rhel_ver> of branch)')
    parser.add_argument('--batch', type=str, default=None,
                        help='batch label (from Dockerfile) of the container images')
    parser.add_argument('-Z', '--debug', action='store_true',
                        help='Enable debugging')
    return parser.parse_args()


if __name__ == '__main__':
    args = get_options()
    bw = CachingKojiWrapper(profile='brew')
    bw.load_cache(debug=args.debug)

    if args.batch:
        cs = bw.get_matching_batch_from_tag(args.osp, args.rhel, args.batch)
    else:
        cs = bw.get_latest_cdn_containers(args.osp, args.rhel, latest=True)

    bw.save_cache(debug=args.debug)

    containers = set()
    for package, builds in cs.items():
        if len(builds) > 1:
            print("More than one build using all {0}".format(package))
        for build in builds.values():
            nvr = build['nvr']
            build_id = build['build_id']
            if build_id not in containers:
                print("Adding {0}: {1}".format(nvr, build_id))
                containers.add(build_id)
                parent_id = bw.getParentBuildId(build_id)
                while parent_id is not None:
                    if parent_id not in containers:
                        print("Parent {0}: {1}".format(bw.get_nvr(parent_id),
                                                       parent_id))
                        containers.add(parent_id)
                        parent_id = bw.getParentBuildId(parent_id)
                    else:
                        break

    package_dict = {}

    for build_id in containers:
        package_name = bw.get_package_name(build_id)
        if package_name in package_dict:
            print("Conflict - duplicates in tree [{0}] ({1}, {2})".format(
                  package_name, build_id, package_dict[package_name]))
            continue

        package_dict[package_name] = build_id

    for build_id in containers:
        if bw.getParentBuildId(build_id) is None:
            print("Got Base Image {0}: {1}".format(bw.get_nvr(build_id),
                                                   build_id))
            continue
        print("{0}: {1}".format(bw.get_nvr(build_id), build_id))

    bw.save_cache(debug=args.debug)
