#!/usr/bin/env python

from __future__ import print_function
import argparse
from container_processing.helpers import get_matching_batch_from_tag
from container_processing.helpers import get_latest_cdn_containers
from container_processing.helpers import getRecordForBuild
import container_processing.helpers
from koji_wrapper.base import KojiWrapperBase


def get_options():
    parser = argparse.ArgumentParser()
    parser.add_argument('osp', type=float,
                        help='osp version to work with')
    parser.add_argument('--rhel', default=7.5, type=float,
                        help='rhel version to work with')
    parser.add_argument('registry_tag', type=str,
                        help='container registry tag desired')
    parser.add_argument('batch', type=str,
                        help='batch label (from Dockerfile) of the container images')
    parser.add_argument('-Z', '--debug', action='store_true',
                        help='Enable debugging')
    parser.add_argument('--from-file', type=str,
                        help='list of container images to use from a file, '
                        'single container image per line please')
    parser.add_argument('--skip-latest', default=False, action='store_true',
                        help='skip tagging as :latest')
    parser.add_argument('--from-cdn', default=False, action='store_true',
                        help='Default to using cdn content if no other images available')
    return parser.parse_args()


def main():

    args = get_options()

    container_processing.helpers.load_cache()

    koji_session = KojiWrapperBase(profile='brew')
    # using latest
    # might also want to use latest from batch
    print('# Checking on builds for rhos-{0}-rhel-{1}'.format(args.osp, args.rhel))
    print('oc login')

    cdn_data = {}
    from_file = {}
    if args.from_cdn:
        cdn_data = get_latest_cdn_containers(args.osp, args.rhel)

    if args.from_file:
        from_file = []
        with open(args.from_file) as fin:
            row = fin.readline()
            while row:
                row = row.rstrip()
                record = getRecordForBuild(koji_session, row)
                from_file[record['package_name']] = [record]
                row = fin.readline()

    data = {}
    for key in set(from_file.keys()) | set(cdn_data.keys()):
        if key in cdn_data:
            data[key] = cdn_data[key]
        if key in from_file:
            data[key] = from_file[key]

    if not data:
        data = get_matching_batch_from_tag(args.osp, args.rhel, args.batch)

    for record_list in data.values():
        if len(record_list) > 1:
            print("Multiple records found picking one {0}".format(record_list))
        record = record_list[0]

        # strip off brew package name plus '-' to leave version-release
        version_release = record['nvr'][len(record['package_name'])+1:]

        # weird construct here to deal with openstack-swift-container-container
        container_name = record['package_name']
        if container_name.endswith('-container'):
            container_name = container_name[0:- len("-container")]

        # form up name:tag of build for oc
        latest_container = "{0}:{1}".format(container_name, version_release)

        # find version-release pullspec
        from_pullspec = None
        for pullspec in record['build_pullspecs']:
            if version_release in pullspec:
                from_pullspec = pullspec
                break
        if from_pullspec is not None:
            print("oc -n rhosp{0} import-image {1} --from \"{2}\" --insecure".format(
                str(int(args.osp)), latest_container, from_pullspec))
        additional_tag = ''
        if not args.skip_latest:
            additional_tag = "{0}:latest".format(container_name)
        print("oc -n rhosp{0} tag {1} {2}:{3} {4}".format(
            str(int(args.osp)), latest_container, container_name,
            args.registry_tag, additional_tag))

    container_processing.helpers.save_cache()

if __name__ == '__main__':
    main()
