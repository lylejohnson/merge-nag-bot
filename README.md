Usage (standalone)
==================

usage: merge_nag_bot [-h] [-p PROJECT_NAME] -t GITLAB_TOKEN -r ROOM_NO -c
                        HIPCHAT_TOKEN

optional arguments:

  -h, --help            show this help message and exit
  
  -p PROJECT_NAME, --namespace PROJECT_NAME
                        namespace of your project, ie core, solar, etc
                        
  -t GITLAB_TOKEN, --gitlab-token GITLAB_TOKEN
                        private token you want to use to log into gitlab (GitLab token is from the Settings->Account->Private Token page)
                        
  -r ROOM_NO, --room-no ROOM_NO
                        hipchat room number
                        
  -c HIPCHAT_TOKEN, --hipchat-token HIPCHAT_TOKEN
                        private token corresponding to hipchat room number

  -i IGNORE_FILE, --ignore-file IGNORE_FILE
                        file with repos that should be ignored

  -s PERIOD, --period PERIOD
                        check for open merge requests every PERIOD hours

