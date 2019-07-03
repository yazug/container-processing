#!/usr/bin/env python

from __future__ import print_function
import argparse
from container_processing.helpers import CachingKojiWrapper
from container_processing.group_test_parse import extract_summary_from_group_test_event

def get_options():
    parser = argparse.ArgumentParser()
    parser.add_argument('osp', type=float,
                        help='osp version to work with')
    parser.add_argument('--rhel', default=7.5, type=float,
                        help='rhel version to work with')
    parser.add_argument('registry_tag', type=str,
                        help='container registry tag desired')
    parser.add_argument('--batch', type=str, default=None,
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
    parser.add_argument('--from-group-testing-json', type=str,
                        help='Filename to load group testing json blob from')
    return parser.parse_args()


def main():

    args = get_options()

    koji_session = CachingKojiWrapper(profile='brew')
    koji_session.load_cache()

    # using latest
    # might also want to use latest from batch
    print('# Checking on builds for rhos-{0}-rhel-{1}'.format(args.osp, args.rhel))
    print('oc login')

    cdn_data = {}
    from_file = {}
    batch_data = {}
    group_test_data = {}

    if args.from_cdn:
        cdn_data = koji_session.get_latest_cdn_containers(args.osp, args.rhel)

    if args.batch:
        batch_data = koji_session.get_matching_batch_from_tag(args.osp, args.rhel, args.batch)

    if args.from_group_testing_json:
        json_blob_string = None
        with open(args.from_group_testing_json) as fin:
            json_blob_string = fin.read()

        if json_blob_string:
            group_test_json = extract_summary_from_group_test_event(json_blob_string)
            for image in group_test_json['images']:
                print([image])
                record = koji_session.getRecordForBuild(image['nvr'])
                group_test_data[record['package_name']] = [record]

    if args.from_file:
        with open(args.from_file) as fin:
            row = fin.readline()
            while row:
                row = row.rstrip()
                record = koji_session.getRecordForBuild(row)

                from_file[record['package_name']] = [record]
                row = fin.readline()

    koji_session.save_cache(debug=True)

    data = {}
    for key in set(from_file.keys()) | set(cdn_data.keys()):
        if key in cdn_data:
            data[key] = cdn_data[key]
        if key in batch_data:
            data[key] = batch_data[key]
        if key in from_file:
            data[key] = from_file[key]
        if key in group_test_data:
            data[key] = group_test_data[key]

    for record_list in data.values():
        if len(record_list) > 1:
            print("# Multiple records found picking one {0}".format(record_list))
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


if __name__ == '__main__':
    main()
