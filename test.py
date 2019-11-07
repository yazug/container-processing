from bs4 import BeautifulSoup
from lxml import html
import os.path
import re
import requests
from requests_gssapi import HTTPSPNEGOAuth
from container_processing.caching_koji import CachingKojiWrapper

GSSAPI_AUTH = HTTPSPNEGOAuth(opportunistic_auth=True)


# from container_processing import lightblue


def fetch_load_container_content(errata_id, cache_path='~/.cache/shale/container_contents/', force_fetch=False):
    """Fetch or load container_content for an advisory

    Returns a parsed html object for this content
    """
    if cache_path is not None:
        cache_path = os.path.expanduser(cache_path)

        if not os.path.isdir(cache_path):
            os.makedirs(cache_path)

    cache_file = 'container_content-{0}'.format(errata_id)
    cache_full_path = os.path.join(cache_path, cache_file)

    html = None
    if os.path.exists(cache_full_path) and not force_fetch:
        with open(cache_full_path, 'r') as fin:
            html = fin.read()

    if html is None:
        print("===== Fetching container_content from ET for {0} ======".format(errata_id))
        tmpl = 'https://errata.devel.redhat.com/container/container_content/%d'
        url = tmpl % errata_id
        response = requests.get(url, auth=GSSAPI_AUTH)
        response.raise_for_status()
        with open(cache_full_path, 'wb') as fout:
            fout.write(response.content)
        html = response.content
    else:
        print("===== Loading container_content from cache for {0} ======".format(errata_id))

    if html is not None:
        return BeautifulSoup(html, 'html.parser')


parsed_html = fetch_load_container_content(47518)


def summarize_advisories(parsed_html):
    """extract and summarize content from container_content

    set of Advisories contibuting data
    set of container images included
    """

    container_images = set()
    advisories = {}
    advisory_details = {}
    for item in parsed_html.find_all('div', attrs={'class': "errata-item"}):
        for link in item.find_all('a'):
            if 'openstack-' in link.text and '-container' in link.text:
                container_images.add(link.text)

            if 'RHSA' in link.text or 'RHBA' in link.text or 'RHEA' in link.text:
                advisory = link.text
                advisory_details[advisory] = link.parent.parent.text.replace('\n', ' ')
                for state in ('SHIPPED', 'NEW_FILES', 'QE', 'REL PREP', 'PENDING', 'PUSH READY', 'IN PUSH', 'NEW FILES'):
                    if state in link.parent.parent.text:
                        break
                else:
                    state = 'OTHER'

                if state not in advisories:
                    advisories[state] = set()
                advisories[state].add(link.text)

    return {
        'container_images': container_images,
        'advisories': advisories,
        'advisory_details': advisory_details
    }


# Extracted from lightblue.py
class ScrapeError(Exception):
    pass


# Extracted from lightblue.py
def container_vulnerabilities(errata_id, brew_build_id, container_content_id):
    """Return the vulnerabilities for this container.

    This loads an HTML page from the Errata Tool and screen-scrapes the CVE
    data.

    Example:
    {'CVE-2016-10745': {'severity': 'Important'
                        'errata-link': 'RHSA-2019:1022',
                        'packages': {'python-jinja2-2.7.2-2.el7cp.noarch'},
                        }}

    :param int errata_id: container ET advisory ID
    :param int brew_build_id: container build in Brew
    :param int container_content_id: ET identifier for an image. This is
                                     unique for each build's archive.
    :returns: A dict of CVEs. Each dict key is the CVE identifier. Each dict
              value is another dict with "severity", "errata-link", and
              "packages" keys."""
    tmpl = 'https://errata.devel.redhat.com/container/modal_container_vulnerabilities/%d?brew_build_id=%d&container_content_id=%d'  # NOQA E501
    url = tmpl % (errata_id, brew_build_id, container_content_id)
    doc = None
    cache_file = 'modal_container_vulnerabilities-{0}-{1}-{2}'.format(errata_id, brew_build_id, container_content_id)
    if os.path.exists(cache_file):
        with open(cache_file, 'rb') as fin:
            doc = html.fragment_fromstring(fin.read(), create_parent='div')

    if doc is None:
        response = requests.get(url, auth=GSSAPI_AUTH)

        with open(cache_file, 'wb') as fout:
            fout.write(response.content)
        response.raise_for_status()

        doc = html.fragment_fromstring(response.content, create_parent='div')

    data = parse_cve_data(doc)
    data['errata_id'] = errata_id
    data['brew_build_id'] = brew_build_id
    data['container_content_id'] = container_content_id

    return data

# Severity ratings in descending order of importance
SEVERITIES = ('Critical', 'Important', 'Moderate', 'Low')


# Extracted from lightblue.py
def parse_cve_data(doc):
    """Parse this lxml Element's children for vulnerability data.

    This parses an lxml Element from the modal_container_vulnerabilities
    Errata Tool page.

    :returns dict: data about the CVEs."""
    cve_data = {}

    vulns = doc.xpath('//li[@class="vulnerability-item"]')
    for vuln in vulns:
        # content = vuln.text_content().strip()
        # print(content)
        children = vuln.getchildren()
        for child in children:
            if 'severity' in child.classes:
                severity = child.text_content().strip()
                if severity not in SEVERITIES:
                    raise ScrapeError('unknown severity: "%s"' % severity)
            elif 'cve-link' in child.classes:
                cve = child.text_content().strip()
                if not re.match(r'^CVE-\d\d\d\d-\d+$', cve):
                    raise ScrapeError('"%s" does not look like a CVE' % cve)
            elif 'errata-link' in child.classes:
                errata = child.text_content().strip()
            elif child.attrib['href'] == '#affected':
                # Get the affected packages from the inline encoded HTML.
                packages = set()
                data_content = child.attrib['data-content']
                ul = html.fragment_fromstring(data_content)
                ul_children = ul.getchildren()
                for ul_child in ul_children:
                    package = ul_child.text_content().strip()
                    packages.add(package)
            else:
                print(child.classes)
                print(child.text_content().strip())
                raise ScrapeError('error parsing %s tag' % child.tag)
        cve_data[cve] = {'severity': severity, 'errata-link': errata,
                         'packages': packages}
    return cve_data


def summarize_cves(parsed_html):
    # Look for CVE's images are vulnerable to
    # TODO(jschluet) Look about how to determine if we should look or not before we actually do
    #     Also check to see if we can simplify or pull the lightblue.container_vulnerabilities() call in if we need to parse/process it differently
    cve_vulnerabilities = []
    for div in parsed_html.find_all('div', attrs={'class': 'modal'}):
        #for link in div.sibling_before():
        #    if 'openstack-' in link.text and '-container' in link.text:
        #        container_images.add(link.text)
        data_remote_url = div['data-remote-url']
        errata_id = data_remote_url.split('?')[0].split('/')[-1]
        (brew_build_id, container_content_id) = [j[1] for j in [i.split('=') for i in data_remote_url.split('&')]]
        # TODO(jschluet) make sure we are using a cache_path for coordinating storage of and cleanup of these files
        lb_data = container_vulnerabilities(int(errata_id), int(brew_build_id), int(container_content_id))
        # lookup and log brew_build_id to brew build
        cve_vulnerabilities.append(lb_data)

    return cve_vulnerabilities


def summarize_installed(parsed_html, debug=False):
    data = {}
    for i in parsed_html.find_all('div', attrs={'class': 'section_container'}):
        container_image = None
        for z in i.find_all('h3'):
            if 'Build' in z.text:
                for build in z.find_all('a'):
                    container_image = build.text
        if debug:
            print(container_image)
        data[container_image] = {}
        for z in i.find_all('a', attrs={'href': '#manifest'}):
            data_str = z['data-content']
            snippit = BeautifulSoup(data_str, 'html.parser')
            for rpm in snippit.find_all('a'):
                if not rpm.text:
                    continue
                rpmid = rpm['href'].split('=')[-1]
                rpm_nvr = rpm.text
                data[container_image][rpmid] = rpm_nvr
                if debug:
                    print([container_image, rpmid, rpm_nvr])
    return data


def summarize_build_info(data, koji_session):
    return_data = {}
    for container in data.keys():
        return_data[container] = {}
        for rpmid in data[container].keys():
            build_id = koji_session.get_build_id_from_rpm_id(int(rpmid))
            return_data[container][build_id] = koji_session.get_nvr(build_id)

            #rpminfo = koji_session.getRPM(int(rpmid))
            #build_id = rpminfo['build_id']
            #if build_id not in return_data[container]:
            #    buildinfo = koji_session.getBuild(build_id)
            #    build_nvr = buildinfo['nvr']
            #    return_data[container][build_id] = build_nvr

    return return_data


def summarize_container_issues(parsed_html):
    # look for container-issues
    error_set = []
    for i in parsed_html.find_all('div', attrs={'class': 'container-issues'}):
        # find container image name by looking back at previous siblings until we find it
        container_image = None
        for j in i.find_all('a'):
            data_str = j['data-content']
            for error in ('RPMs Without Errata', 'Invalid Signatures'):
                if error in data_str:
                    # find name of container_image if we have issues
                    if container_image is None:
                        search_container = i
                        while not [z.text for z in search_container.find_all('a') if 'container' in z.text]:
                            search_container = search_container.find_previous_sibling()
                        container_image = [z.text for z in search_container.find_all('a') if 'container' in z.text][0]
                    snippit = BeautifulSoup(data_str, 'html.parser')
                    for rpm in snippit.find_all('a'):
                        error_set.append({'error': error, 'container_nvr': container_image, 'rpm': rpm.text})
    return error_set

print("==== find advisories ====")
data = summarize_advisories(parsed_html)

print("==== find CVEs ====")
cve_vulnerabilities = summarize_cves(parsed_html)

print("==== find container-issues ====")
error_set = summarize_container_issues(parsed_html)

for key in data['advisories']:
    print(key, data['advisories'][key])
for i in data['advisory_details'].values():
    print(i)
for i in cve_vulnerabilities:
    if [k for k in i.keys() if 'CVE' in k]:
        print(i)
for i in error_set:
    print(i)
