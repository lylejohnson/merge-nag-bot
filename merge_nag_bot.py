#!/usr/bin/env python

import argparse
import datetime
import dateutil.tz
import dateutil.parser
from itertools import chain
import json
import logging
import re
import time
import pytz
import yaml
import humanize

import requests

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class Project(object):
    def __init__(self, project_id, project_namespace, project_name, project_url):
        self.id = project_id
        self.namespace = project_namespace
        self.name = project_name
        self.url = project_url


class MergeRequest(object):
    def __init__(self, merge_request_id, project, description, title, created_at, web_url):
        self.api_base = api_base
        self.id = merge_request_id
        self.project = project
        self.description = description
        self.title = title
        self.created_at = created_at
        self.web_url = web_url

    def is_wip(self):
        """Returns True if this is a WIP branch"""
        return re.search(r"^[\[]?[w,W][i,I][p,P]", self.title)

    def url(self):
        return self.web_url

    def age(self):
        return datetime.datetime.utcnow() - self.created_at


class GitLab(object):
    def __init__(self, api_base, gitlab_token, input_file):
        self._api_base = api_base
        self._headers = {'PRIVATE-TOKEN': gitlab_token}
        self._projects = None
        with open(input_file, 'r') as f:
            namespaces_and_projects_to_scan = yaml.safe_load(f)
            for namespace in namespaces_and_projects_to_scan.iterkeys():
                namespaces_and_projects_to_scan[namespace] = set(namespaces_and_projects_to_scan[namespace])
        logger.debug(namespaces_and_projects_to_scan)
        self._init_projects(namespaces_and_projects_to_scan)

    def projects(self):
        return self._projects.itervalues()

    def get_open_merge_requests(self):
        merge_requests = [self._get_open_merge_requests_for_project(project) for project in self.projects()]
        return [i for i in chain.from_iterable(merge_requests)]

    def _init_projects(self, namespaces_and_projects_to_scan):
        self._projects = {}
        content_length = 10
        pages = 1
        while content_length > 2:
            gitlab_url = "{api_base}/api/v3/projects/?page={pages}&per_page=100".format(api_base=self._api_base, pages=pages)
            pages += 1
            response = requests.get(gitlab_url, headers=self._headers)
            print response.json()
            content_length = int(response.headers['content-length'])
            for project in response.json():
                namespace = project['namespace']['name']
                if namespace in namespaces_and_projects_to_scan.iterkeys():
                    project_name = project['name']
                    if project_name in namespaces_and_projects_to_scan[namespace]:
                        self._projects[project_name] = self._create_project(project)

    @staticmethod
    def _create_project(data):
        return Project(project_id=data['id'], project_namespace=data['namespace']['name'], project_name=data['name'], project_url=data['web_url'])

    def _get_open_merge_requests_for_project(self, project):
        gitlab_url = "{api_base}/api/v3/projects/{project_id}/merge_requests?state=opened".format(
            api_base=self._api_base, project_id=project.id)
        response = requests.get(gitlab_url, headers=self._headers)
        return map(lambda data: self._create_merge_request(project, data), response.json())

    @staticmethod
    def _create_merge_request(project, data):
        created_at = dateutil.parser.parse(data['created_at']).astimezone(pytz.utc).replace(tzinfo=None)
        return MergeRequest(web_url=data['web_url'], merge_request_id=data['iid'],
                            project=project, description=data['description'],
                            title=data['title'], created_at=created_at)


class HipChat(object):
    def __init__(self, api_token, room_number):
        self._room_url = "https://api.hipchat.com/v2/room/{room_number}/notification?auth_token={api_token}".format(
            room_number=room_number, api_token=api_token)
        self._headers = {'Content-Type': 'application/json'}

    def say(self, message, color="yellow"):
        payload = json.dumps(
            {"color": color, "message": message, "notify": 'false', "message_format": "text"})
        return requests.post(self._room_url, payload, headers=self._headers)


class NagBot(object):
    def __init__(self, gitlab, hipchat, warn_period):
        self._gitlab = gitlab
        self._hipchat = hipchat
        self._sleeps_outside_normal_business_hours = True
        self._awake = True
        self._warn_period = warn_period

    def is_awake(self):
        if not self._sleeps_outside_normal_business_hours:
            return True
        else:
            if self._is_normal_business_hours():
                return self.wake_up()
            return self.nod_off()

    def wake_up(self):
        if not self._awake:
            self._hipchat.say("Good morning everyone!", color="green")
            self._awake = True
        return self._awake

    def nod_off(self):
        if self._awake:
            self._hipchat.say("I'm going to take a nap now, but I'll be back to nag you again soon!", color="green")
            self._awake = False
        return self._awake

    def nag(self):
        if self.is_awake():
            try:
                merge_requests = self._gitlab.get_open_merge_requests()
                for merge_request in merge_requests:
                    if not merge_request.is_wip():
                        self._nag_for_merge_request(merge_request)
            except:
                logging.exception("Unable to fetch merge request info from GitLab")
                message = u"Unable to fetch merge request info from GitLab; will try again at next interval"
                say._hipchat.say(message, color="red")

    def _is_late(self, merge_request):
        age_in_seconds = merge_request.age().total_seconds()
        return age_in_seconds > (self._warn_period * 3600)

    def _nag_for_merge_request(self, merge_request):
        message = u"[{project_name}] waiting on merge since {when}: {url} - {title}".format(
            project_name=merge_request.project.name, url=merge_request.url(), title=merge_request.title,
            when=humanize.naturaltime(merge_request.age()))
        self._hipchat.say(message, color="red" if self._is_late(merge_request) else "yellow")

    def _is_normal_business_hours(self):
        """Return True if it's normal business hours, otherwise False."""
        tz = dateutil.tz.gettz("US/Central")
        now = datetime.datetime.now(tz)
        if now.weekday() == 5 or now.weekday() == 6:  # Saturday or Sunday?
            return False
        if now.hour < 6 or now.hour > 17:
            return False
        return True


def main():
    parser = argparse.ArgumentParser(prog='merge_nag_bot')
    parser.add_argument('-b', '--api-base', required=True, help="Prefix for API calls (e.g. https://gitlab.example.com)")
    parser.add_argument('-t', '--gitlab-token', required=True, help="private token you want to use to log into gitlab")
    parser.add_argument('-r', '--room-no', required=True, help="hipchat room number")
    parser.add_argument('-c', '--hipchat-token', required=True,
                        help="private token corresponding to hipchat room number")
    parser.add_argument('-f', '--input-file', default=None, help="name of file with namespaces and projects to scan")
    parser.add_argument('-s', '--period', default=2, help="check for open merge requests every PERIOD hours")
    parser.add_argument('-w', '--warn-period', default=4, help="Merge requests are considered 'old' (turn red instead of yellow) after WARN_PERIOD hours")

    args = parser.parse_args()

    hipchat = HipChat(args.hipchat_token, args.room_no)
    gitlab = GitLab(args.api_base, args.gitlab_token, args.input_file)
    nagbot = NagBot(gitlab, hipchat, args.warn_period)

    while True:
        nagbot.nag()
        time.sleep(int(args.period) * 60 * 60)


if __name__ == "__main__":
    main()
