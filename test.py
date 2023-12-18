import urllib.request
import requests
import urllib
from urllib.request import urlopen
import urllib3

file_url = "https://raw.githubusercontent.com/TomArcherMsft/migrate-terraform-sample/main/prompt_inputs.json"

def t1():
    for line in urllib.request.urlopen(file_url):
        print(line.decode('utf-8')) 

def t2():
    r = requests.get(file_url)
    print(r.text)

t2()