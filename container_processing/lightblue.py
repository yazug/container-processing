#!/usr/bin/python3
from requests_gssapi import HTTPSPNEGOAuth
from lxml import html
import requests
import re
from collections import defaultdict
import os.path



gssapi_auth = HTTPSPNEGOAuth(opportunistic_auth=True)

# Severity ratings in descending order of importance
SEVERITIES = ('Critical', 'Important', 'Moderate', 'Low')


class ScrapeError(Exception):
    pass


def container_contents(errata_id):
    """
    Return a list of tuples: "brew_build_id" and "container_content_id"

    "brew_build_id" (int) is the build identifer for the container in Brew.

    "container_content_id" (int) is unique for each container image in a Brew
    build. If a Brew build is multi-arch (for example), then there will be
    one container_content_id for x86_64 and another one for ppc64le.
    I don't know much else about this parameter. I'm not sure if/how it
    relates to Lightblue's representation of container contents, or if it is
    just an ET thing.

    :param int errata_id: container ET advisory ID
    """
    tmpl = 'https://errata.devel.redhat.com/container/container_content/%d'
    url = tmpl % errata_id
    cache_file = 'container_content-{0}'.format(errata_id)
    doc = None
    if os.path.exists(cache_file):
        with open(cache_file, 'rb') as fin:
            doc = html.document_fromstring(fin.read())

    if doc is None:
        response = requests.get(url, auth=gssapi_auth)
        response.raise_for_status()
        with open(cache_file, 'wb') as fout:
            fout.write(response.content)
        doc = html.document_fromstring(response.content)


    divs = doc.xpath('//div[starts-with(@id, "container_vulnerabilities_modal_")]')  # NOQA E501
    results = []
    for div in divs:
        remote_url = div.attrib['data-remote-url']
        match = re.search(r'brew_build_id=(\d+)', remote_url)
        if not match:
            raise ScrapeError(remote_url)
        brew_build_id = int(match.group(1))
        match = re.search(r'container_content_id=(\d+)', remote_url)
        if not match:
            raise ScrapeError(remote_url)
        container_content_id = int(match.group(1))
        results.append((brew_build_id, container_content_id))
    return results


def container_vulnerabilities(errata_id, brew_build_id, container_content_id):
    """
    Return the vulnerabilities for this container.

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
              "packages" keys.
    """
    tmpl = 'https://errata.devel.redhat.com/container/modal_container_vulnerabilities/%d?brew_build_id=%d&container_content_id=%d'  # NOQA E501
    url = tmpl % (errata_id, brew_build_id, container_content_id)
    doc = None
    cache_file = 'modal_container_vulnerabilities-{0}-{1}-{2}'.format(errata_id, brew_build_id, container_content_id)
    if os.path.exists(cache_file):
        with open(cache_file, 'rb') as fin:
            doc = html.fragment_fromstring(fin.read(), create_parent='div')

    if doc is None:
        response = requests.get(url, auth=gssapi_auth)

        with open(cache_file, 'wb') as fout:
            fout.write(response.content)
        response.raise_for_status()

        doc = html.fragment_fromstring(response.content, create_parent='div')

    data = parse_cve_data(doc)
    data['errata_id'] = errata_id;
    data['brew_build_id'] = brew_build_id
    data['container_content_id'] = container_content_id

    return data


def parse_cve_data(doc):
    """
    Parse this lxml Element's children for vulnerability data.

    This parses an lxml Element from the modal_container_vulnerabilities
    Errata Tool page.

    :returns dict: data about the CVEs.
    """
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


def summarize_vulnerabilities(cve_data):
    """
    Return a human-readable description of the most severe vulnerabilit(es).

    Examples:
      "an Important vulnerability"
      "2 Critical vulnerabilities"
    """
    severity_counts = defaultdict(int)
    if not cve_data:
        return "No cve vulnerabilities found"

    for cve in cve_data.values():
        severity = cve['severity']
        severity_counts[severity] += 1
    for severity in SEVERITIES:
        if severity in severity_counts:
            count = severity_counts[severity]
            if count == 1:
                return 'an %s vulnerability' % severity
            return '%d %s vulnerabilities' % (count, severity)
    raise RuntimeError('could not describe severity in %s' % cve_data)


def detail_vulnerabilities(cve_data):
    """
    List the details of all vulnerabilites.

    Examples:
    Important CVE-2019-6454 https://access.redhat.com/errata/RHSA-2019:0368

    Vulnerable package versions:
      systemd-219-62.el7_6.2
      systemd-libs-219-62.el7_6.2
    """
    lines = []
    all_packages = set()
    for cve_id, cve in cve_data.items():
        severity = cve['severity']
        advisory = cve['errata-link']  # eg "RHSA-2019:1022"
        url = 'https://access.redhat.com/errata/%s' % advisory
        line = '%s %s %s' % (severity, cve_id, url)
        lines.append(line)
        packages = cve['packages']
        for package in packages:
            nvr, _ = package.rsplit('.', 1)
            all_packages.add(nvr)

    lines.append('')
    lines.append('Vulnerable package versions:')
    for package in all_packages:
        lines.append('  %s' % package)

    text = "\n".join(lines)
    return text


def describe(errata_id, cve_data):
    summary = summarize_vulnerabilities(cve_data)
    details = detail_vulnerabilities(cve_data)

    template = """\
Our container includes packages that are vulnerable to
{summary}.

{details}

This bug tracks rebuilding the container against the newer base container
image with the fixed packages.
"""
    result = template.format(summary=summary, details=details)
    return result


def main(errata_id):
    containers = container_contents(errata_id)
    from pprint import pprint
    pprint(containers)
    for container in containers:
        (brew_build_id, container_content_id) = container
        cve_data = container_vulnerabilities(errata_id, brew_build_id,
                                             container_content_id)
        if cve_data:
            pprint(cve_data)
            text = describe(errata_id, cve_data)
            print(text)

