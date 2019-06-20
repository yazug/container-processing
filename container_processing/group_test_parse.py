"""Helper module to parse container images from group test event message"""

import json


def extract_summary_from_group_test_event(json_blob_string):
    """Extract details from group test event message"""
    json_blob = json.loads(json_blob_string)

    ret_data = {}
    message_id = json_blob['headers']['message-id']
    containers = []
    errata_id = json_blob['msg']['artifact']['errata_id']
    for i in json_blob['msg']['artifact']['images']:
        blob = {}
        for key in ['nvr', 'full_name', 'namespace', 'tag']:
            blob[key] = i[key]
        containers.append(blob)
    ret_data = {'message_id': message_id, 'errata_id': errata_id,
                'images': containers}
    return ret_data


def main():
    """Main for taking file with Group Test json message

    outputs list of container images in message
    """

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('test_file', type=str,
                        help="json file with group_test blob in it")
    parser.add_argument('--debug', action='store_true', default=False,
                        help='Enable additional debugging output')

    args = parser.parse_args()

    json_blob_string = None
    with open(args.test_file) as fin:
        json_blob_string = fin.read()

    if json_blob_string:
        containers = extract_summary_from_group_test_event(json_blob_string)
        if args.debug:
            print(containers)

        for i in containers['images']:
            print(i['nvr'])


if __name__ == '__main__':
    main()
