#!/usr/bin/python
#Shorthand command for running searx via docker: docker run -p8888:8888 <instancename>/searx
import os, requests, smtplib, time, argparse, logging
import getpass as pw
import httplib as http_client
from email.mime.text import MIMEText
from argparse import RawTextHelpFormatter
from email_validator import validate_email, EmailNotValidError


def get_mail(smtpinfo):
    email = raw_input("Please enter email address to send to use: ")
    try:
        v = validate_email(email) # validate and get info
        email = v["email"] # replace with normalized form
    except EmailNotValidError as e:
        # email is not valid, exception message is human-readable
        print(str(e))
        exit(1)

    return email


def pw_verify():
    flag = 1
    while flag == 1:
        pwd = pw.getpass("Enter password for email account: ")
        pwd2 = pw.getpass("Enter password again: ")
        if pwd == pwd2:
            flag = 0
        else:
            print "Passwords did not match, try again"

    return pwd


def get_keywords(keylist):
    with open(keylist, "r") as f:
            file_contents = f.read()
            keywords = file_contents.splitlines()
            f.close()

    return keywords

def createDir(name):
    cwd = os.getcwd()
    directory = cwd + "/%s" % (name)
    if not os.path.exists(directory):
        os.makedirs(directory,0644)
        print "[*] Directory For %s Not Found" % (name)
        print "[!] Directory For %s Created..." % (name)
    else:
        print "[?] Directory For %s Already Exists" % (name)
    return directory


#send the email to me
def send_alert(ename, alert_email, pwd, smtpinfo):
    tSearx = 0
    tPastebin = 0

    subject = "KAS: "
    terminal = "[*] "
    if alert_email.has_key("searx"):
        tSearx = len(alert_email['searx'].keys())
        subject += "%s searx " % str(tSearx)
        terminal += "%s searx " % str(tSearx)
    if alert_email.has_key("pastebin"):
        tPastebin = len(alert_email['pastebin'].keys())
        subject += "%s pastebin " % str(tPastebin)
        terminal += "%s pastebin " % str(tPastebin)

    subject += "found"
    terminal += "found"
    print terminal

    alert_email_account = ename
    alert_email_password = pwd

    email_body = "The following are keyword hits that were just found:\r\n\r\n"
    #walk through the searx results from active scan
    if alert_email.has_key("searx"):
        total = 0
        for keyword in alert_email['searx']:
            i = 1
            email_body += "\r\n[%d] hits for Keyword: %s\r\n\r\n" % (len(alert_email['searx'][keyword]),keyword)
            for keyword_hit in alert_email['searx'][keyword]:
                email_body += "%d. %s\r\n" % (i, keyword_hit)
                i = i+1
                total = total + 1

    #walkthrough pastebin results
    if alert_email.has_key("pastebin"):

        for paste_id in alert_email['pastebin']:
            email_body += "\r\nPastebin Link: https://pastebin.com/%s\r\n" % (paste_id)
            email_body += "Keywords:%s\r\n" % ",".join(alert_email['pastebin'][paste_id][0])
            email_body += "Paste Body:\r\n%s\r\n\r\n" % alert_email['pastebin'][paste_id][1]
            total = total + 1

    email_body += "\r\n[%d] Total Hits found by K.A.S\r\n" % (total)
    print "[*] Total hits: %d " % (total)
    print "[*] SMTP to use: %s" % (smtpinfo)
    #build up the message
    msg = MIMEText(email_body)
    msg['Subject'] = subject
    msg['From'] = alert_email_account
    msg['To'] = alert_email_account

    if smtpinfo == "gmail":
        server = smtplib.SMTP("smtp.gmail.com",587)
        server.ehlo()
        server.starttls()
        server.login(alert_email_account,alert_email_password)
        server.sendmail(alert_email_account,alert_email_account,msg.as_string())
        server.quit()
    
    else:
        server = smtplib.SMTP("smtp.office365.com", 587)
        server.ehlo()
        server.starttls()
        server.login(alert_email_account,alert_email_password)
        server.sendmail(alert_email_account,alert_email_account,msg.as_string())
        server.quit()

    print "[!] Alert email sent!"

    return

#check if the URL is new
def check_urls(dirpath,keyword,urls):

    new_urls = []

    if os.path.exists(dirpath+"/%s.txt" % keyword):
        with open(dirpath+"/%s.txt" % keyword,"r") as fd:
            stored_urls = fd.read().splitlines()

        for url in urls:
            if url not in stored_urls:
                print "[*] New URL for %s discovered: %s" % (keyword,url)
                new_urls.append(url)
    else:
        new_urls = urls

    # now store the new urls back in the file
    with open(dirpath+"/%s.txt" % keyword,"ab") as fd:

        for url in new_urls:
            fd.write("%s\r\n" % url)

    return new_urls


# call the running Searx service for keyword.
def check_searx(dirpath, keyword, timerange, category):
    searx_url = "http://localhost:8888/?"
    hits = []
    time_range = {'day','week','month','year'}
    categories_type = {'images','files', 'social+media'}
    #build paramter dictionary
    params               = {}
    params['q']          = keyword

    if category in categories_type:
        params['categories'] = category
    else:
        params['categories'] = 'general'

    if timerange in time_range:
        params['time_range'] = timerange #day,week,month or year will work

    params['format'] = 'json'

    print "[*] Querying Searx for: %s" % keyword
    # send the request off to searx
    try:
        response = requests.get(searx_url,params=params)
        results  = response.json()
    except:
        return hits

    # if results are found, check them against the stored URLs
    if len(results['results']):
        urls = []

        for result in results['results']:
            if result['url'] not in urls:
                urls.append(result['url'])

        hits = check_urls(dirpath,keyword,urls)

    return hits


#Check pastebin for keyword list
def check_pastebin(dirpath,keywords):

    new_ids = []
    paste_hits = {}
    #call the Pastebin API (HTTPS version)
    try:
        response = requests.get("https://pastebin.com/api_scraping.php?limit=500").json()
    except:
        return paste_hits
    #parse json data
    result = response.json()
    #load pasteid list and only check one's that do not exist
    if os.path.exists(dirpath+"/pastebin_ids.txt"):
        with open(dirpath+"/pastebin_ids.txt","rb") as fd:
            pastebin_ids = fd.read().splitlines()
    else:
        pastebin_ids = []

    for paste in result:
        if paste['key'] not in pastebin_ids:

            new_ids.append(paste['key'])
            #this is a new paste so send a secondary request to retrieve it all
            #then check it for keywords
            paste_response = requests.get(paste['scrape_url'])
            paste_body_lower = paste_response.content.lower()

            keyword_hits = []

            for keyword in keywords:
                if keyword.lower() in paste_body_lower:
                    keyword_hits.append(keyword)

            if len(keyword_hits):
                paste_hits[paste['key']] = (keyword_hits,paste_response.content)
                print "[*] Hit on Pastebin for %s: %s" % (str(keyword_hits),paste['full_url'])

    # store the newly checked IDs
    with open(dirpath+"/pastebin_ids.txt","ab") as fd:
        for pastebin_id in new_ids:
            fd.write("%s\r\n" % pastebin_id)

    print "[*] Successfully processed %d Pastebin posts." % len(new_ids)

    return paste_hits


#wrapper function
def check_keywords(dirpath, keywords, timerange, category):

    max_sleep_time = 120
    alert_email = {}
    time_start = time.time()

    #use the list of keywords and check each against searx
    for keyword in keywords:
        #query searx for the keyword
        result = check_searx(dirpath, keyword, timerange, category)
        if len(result):
            if not alert_email.has_key("searx"):
                alert_email['searx'] = {}
            alert_email['searx'][keyword] = result

    # now check Pastebin for new pastes
    result = check_pastebin(dirpath,keywords)

    if len(result.keys()):
        #results automatically get included into email
        alert_email['pastebin'] = result

    time_end = time.time()
    total_time = time_end - time_start

    # if we complete the above inside of the max_sleep_time setting
    # we sleep. This is for Pastebin rate limiting
    if total_time < max_sleep_time:
        sleep_time = max_sleep_time - total_time
        print "[*] Sleeping for %d s" % sleep_time
        time.sleep(sleep_time)
    return alert_email

#perform the main loop

if __name__=="__main__":
    parser = argparse.ArgumentParser(description="""OSINT Keyword Alert System program - created by killerb33s

                OpenSource intellegence gathering program designed to search for
                keywords across a self-hosted privacy-respecting metasearch engine.
                The keywords are also used in conjuction to search for any data dumps
                onto pastebin. Interval of total time per list search is 2 minutes.
                
                May need to set permissions for your gmail to be allowed through this 
                program (its technically a mail client). Outlook or O365 uses microsoft 
                email servers. """,
                                                    usage='%(prog)s [OPTIONS] -e microsoft -l KEYWORDS -o OUTPUTFOLDER',
                                                    formatter_class=RawTextHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Set verbose output")
    parser.add_argument("-e", "--email", dest="email", type=str,
                        choices=['gmail', 'o365', 'none'], default="none",
                        help="Send Email through Gmail or O365 SMTP servers only")
    parser.add_argument("-r", "--range", dest="range", type=str,
                        choices=['day','week','month','year','any'], default="any",
                        help="Specific time range to look for keywords. DEFAULT: any")
    parser.add_argument("-c", "--category", dest="category", type=str,
                            choices=['images','files','socialmedia','general'], default="general",
                            help="Type of category for keyword to look for. DEFAULT: general")
    required = parser.add_argument_group('required arguments')
    required.add_argument("-l", "--list",  dest="keywords", type=str, required=True,
                        help="List of Keywords to Scan")
    required.add_argument("-o", "--folder",  dest="outputfolder", type=str,required=True,
                        help="Folder to dump keywords into (Will create if it does not exist)")
    args = parser.parse_args()

    #enable logging if verbose set(debugging purposes)
    if args.verbose:
        http_client.HTTPConnection.debuglevel = 1
        logging.basicConfig()
        logging.getLogger().setLevel(logging.DEBUG)
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True

    #change type
    category = args.category
    if category == "socialmedia":
        category = "social+media"

    print"K.A.S. parameters for search are time range:[%s], category:[%s]" % (args.range, category)

    dirpath = createDir(args.outputfolder)
    
    if args.email == "none":
        while True:
            keywords = get_keywords(args.keywords)
            alert_email = check_keywords(dirpath, keywords, args.range, category)

    else:
        ename = get_mail(args.email)
        pwd = pw_verify()
        while True:
            keywords = get_keywords(args.keywords)
            alert_email = check_keywords(dirpath, keywords, args.range, category)
            if len(alert_email.keys()):
            # if there are alerts go ahead and send them via email
                send_alert(ename,alert_email, pwd, args.email)
