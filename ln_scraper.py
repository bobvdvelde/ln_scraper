"""

Lexis Nexis scraper NL 

Scraper for the Dutch Lexis Nexis Academic service. This scraper is ONLY intended 
for research purposes by subscribers to this service. DO NOT USE OUTSIDE A PAID
SUBSCRIPTION. 

"""
import optparse
import logging
import time
import random
from selenium import webdriver
import platform
import tqdm
import datetime
from lxml.html import fromstring
import os
import pickle
from selenium.webdriver.common.keys import Keys

logger = logging.getLogger(__name__)
logging.basicConfig(level="INFO")

BASE_URL       = "http://academic.lexisnexis.nl"
TIMEOUT_SEC    = 2
TIMEOUT_JITTER = 1
VERBOSE        = True
STATUSFILE     = 'status.pkl'

def retry(attempts, func, *args, **kwargs):
    for i in range(attempts):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.debug("Failed attempt {i} of {func}, args: {args}, kwargs {kwargs}: {e}".format(**locals()))
            time.sleep(1)
            return "FAILED"

def timeout():
    ''' applies timeout based on globals '''
    timeout_sec = TIMEOUT_SEC
    if TIMEOUT_JITTER:
        timeout_sec += random.randrange(-1*TIMEOUT_JITTER*10,TIMEOUT_JITTER*10)/10
    logger.debug('sleeping {TIMEOUT_SEC} + {TIMEOUT_JITTER} = {timeout_sec}'.format(
        TIMEOUT_SEC=TIMEOUT_SEC, TIMEOUT_JITTER=TIMEOUT_JITTER, timeout_sec=timeout_sec))
    time.sleep(timeout_sec)

def _make_driver(driver='Firefox', **kwargs):
    if driver=='Firefox':
        drivername = 'geckodriver'

    ostype = platform.system()
     
    driverpath = "./{drivername}_{ostype}".format(**locals())

    kwargs.update({"executable_path" : driverpath })

    logger.debug("creating {driver} webdriver on {ostype} with the arguments:".format(**locals()))
    logger.debug(kwargs)

    wdriver    = getattr(webdriver,driver)(**kwargs)

    return wdriver

def _toframe(driver,xpath):
    driver.switch_to_frame(driver.find_element_by_xpath(xpath))

def main(driver, country=None, source=None, fromdate=None, todate=None, query="a"):

    if not todate:
        todate = datetime.datetime.now()

    if not fromdate:
        fromdate = todate - datetime.timedelta(days=1)

    driver = initialize_sources_page(driver)
    
    if not country:
        countries = get_countries(driver)
        return countries

    if country and not source:
        driver, countries = get_countries(driver, country)
        sources           = scan_pages_for_sources(driver)
        return sources
     
    if country and source:
        driver, _ = get_countries(driver, country)
        pages     = get_pages(driver)

        driver          = go_and_select_source(driver, source)
        driver          = push_go(driver)
        driver.switch_to_default_content()
        driver, results = search(driver, fromdate, todate, query)

        return results
    return "Unknown parameters"

def _querystring(country,sources):
    return "{country}-{sources}".format(**locals())

def search_back_by_day( country, sources, startdate=None, enddate=datetime.datetime(1,1,1,1), query="a"):
    if not 'data' in os.listdir('.'):
        os.mkdir('data')

    if STATUSFILE in os.listdir('.'):
        status = pickle.load(open(STATUSFILE,'rb'))
        startdate = status.get(_querystring(country,sources), None)
    else:
        status = {}

    if not startdate: 
        startdate = datetime.datetime.now()

    driver = _make_driver()
    logger.info("starting at {startdate}".format(**locals()))

    while startdate > enddate:
        logger.info("Now at {startdate}".format(**locals()))
        for source in tqdm.tqdm(sources, disable=not VERBOSE, desc="getting %s" %startdate):
            resultfile = '{source}_{startdate}.pkl'.format(**locals())
            if resultfile in os.listdir('data'): continue
            results = main(driver, country, source, todate=startdate, query=query)
            pickle.dump(results, open(os.path.join('data',resultfile) ,'wb'))
        startdate = startdate - datetime.timedelta(days=1)
        status[_querystring(country,sources)] = startdate
        pickle.dump(status, open(STATUSFILE,'wb'))
    driver.quit()
    

def initialize_sources_page(driver):    
    logger.info("Initializing driver")
    driver.get(BASE_URL)
    time.sleep(3)
    driver.switch_to_frame('mainFrame')
    time.sleep(1)
    el = retry(4, driver.find_element_by_link_text, "Sources")
    el.click()
    time.sleep(5)
    driver    = _go_to_main(driver)
    driver    = go_to_alpha(driver)


    return driver
    
def go_and_select_source(driver, source):
    driver = _go_to_main(driver)
    driver = go_to_alpha(driver)
    pages  = get_pages(driver)
    if "0-9" in pages: 
        driver = go_to_page(driver,"0-9")
        return go_and_select_source(driver,source)

    for word in source.split():
        let = word.capitalize()[0]
        logger.info('Looking under {let}'.format(**locals()))
        pages  = get_pages(driver)

        if let in pages.keys():
            driver = go_to_page(driver,let)
        elif "0-9" in pages.keys():
            driver = go_to_page(driver, "0-9")
        else:
            logger.warning("There does not seem to be a sources pages {let} for source {source}".format(**locals()))
            continue

        driver, success = find_and_click_source(driver,source)
        if success: break
        else:
            go_to_page(driver, "0-9")


    return driver

def find_and_click_source(driver, source):

    nextpage = True

    while nextpage:

        driver = _go_to_main(driver)
        page_sources = get_sources(driver)

        if source in page_sources:
            driver = get_sources_frame(driver)
            driver.find_element_by_xpath('//*[text()="%s"]' %source).click()
            return driver, True
        
        driver = get_sources_frame(driver)
        try:    nextpage = driver.find_element_by_xpath('//*[@title="View Next"]')
        except: break
        logger.info("{source} not found on page, moving to next".format(**locals()))
        nextpage.click()

    return driver, False

def push_go(driver):
    driver     = _go_to_main(driver)
    driver     = get_sources_frame(driver)
    go_button  = driver.find_element('id','selectButtonBottomRed')
    go_button.click()
    return driver

def search(driver, fromdate, todate, query):
    driver = _focus_search_main(driver)
    _go_set_query(driver, fromdate, todate, query)
    driver.find_element_by_xpath('//*[@type="submit"]').click()
    if "none of your terms are searchable words" in driver.page_source:
        raise Exception("Search terms not accepted :-(")
    driver, results = paginate_search(driver)
    return driver, results

def _focus_search_main(driver):
    logger.debug("Resetting driver page position")
    driver.switch_to_default_content()
    driver.switch_to_frame('mainFrame')
    time.sleep(1)
    return driver

def _go_set_query(driver, fromdate, todate, query):
    time.sleep(1)
    def setdate():
        try: 
            driver.find_element_by_xpath('//option[@value="from"]').click()
            assert driver.find_element('id','fromDate1').is_displayed()
        except: 
            driver.find_element('id','dateSelector1').click()
            driver.find_element('id','dateSelector1').send_keys('Date is between .')
            driver.find_element('id','dateSelector1').send_keys(Keys.ENTER)
            assert driver.find_element('id','fromDate1').is_displayed() 
            
    
    retry(6, setdate)
    time.sleep(2)
    makestring  = lambda x: "%02d/%02d/%s" %(x.day, x.month, x.year)
    driver.find_element('id','fromDate1').send_keys(makestring(fromdate ))
    driver.find_element('id','toDate1'  ).send_keys(makestring(todate   ))
    driver.find_element('id','terms'    ).send_keys(query)

def paginate_search(driver):

    all_results = []
    nextpage = True

    driver = _focus_search_main(driver)

    while nextpage:
        driver, results = retry(10, get_results,driver)
        all_results.extend(results)
        
        try:    nextpage = retry(3,driver.find_element_by_xpath,'//a[@class="icon la-TriangleRight "]')
        except: 
            nextpage = None 
            break
        
        if nextpage and nextpage!="FAILED": nextpage.click()
        else: break

    return driver, all_results        

def get_results(driver):
    driver         = _focus_search_main(driver)

    def ga(byline):
        if "\n" in byline: 
            return byline.split("\n")
        else:
            return byline, ""

    retry(10, driver.find_element_by_xpath, '//ol[@class="nexisresult"]//h2/a')
    
    # Result properties
    result_urls    = [ ref.get_property('href') for ref in driver.find_elements_by_xpath('//ol[@class="nexisresult"]//h2/a')]
    result_source  = [ ref.text for ref in driver.find_elements_by_xpath('//li[@class="src"]/span')]
    result_bylines = [ ref.text for ref in driver.find_elements_by_xpath('//li[@class="src byline secByline"]')]
    result_dates   = [ ref.text for ref in driver.find_elements_by_xpath('//li[@class="pubdate"]')]
    result_nhits   = [ ref.text for ref in driver.find_elements_by_xpath('//p[@class="hitsinfo"]')]

    results = [dict(url        = url, 
                    source     = source, 
                    byline     = byline, 
                    firstline  = ga(byline)[0], 
                    secondline = ga(byline)[1], 
                    date       = date, 
                    hits       = nhits ) for 
                    url, source, byline, date, nhits in zip(result_urls, result_source, result_bylines, result_dates, result_nhits)
                ]
    time.sleep(1)
    
    for n, result in enumerate(tqdm.tqdm(results,disable=not VERBOSE, desc="parsing results")):
        driver, page_content = get_result(driver, n)
        result.update(page_content)
        driver = _focus_search_main(driver)
        refreshable = 0
        while retry(10, driver.find_element_by_xpath, '//ol[@class="nexisresult"]//h2/a') == "FAILED":
            driver.refresh()
            if refreshable == 10: break
            refreshable +=1
    time.sleep(1)
    return driver, results 

def get_result(driver, resultnumber):
    '''
    Get a specific result's text body and addition information starting from the results page.
    '''
    # go to result
    driver = _focus_search_main(driver)
    retry(10, driver.find_element, 'id','results')
    time.sleep(5)
    retry(10, driver.find_element_by_xpath, '//ol[@class="nexisresult"]//h2/a' )
    links  = [ ref for ref in driver.find_elements_by_xpath('//ol[@class="nexisresult"]//h2/a')]
    item = retry(10, links.__getitem__,resultnumber)
    item.click()
    
    fon = lambda x: driver.find_elements_by_xpath(x) and driver.find_element_by_xpath(x).text or ""
    # get content
    result = {}
    retry(10, driver.find_element, 'id','document')
    result['raw']     = driver.page_source
    result['excerpt'] = fon('//span[@class="SS_L0"]')
    result['body']    = '\n'.join([t.text for t in driver.find_elements_by_xpath('//p[@class="loose"]')])

    result.update(_get_caps(driver))

    # return home
    driver.back()    
    time.sleep(1)
    if retry(10, driver.find_element_by_xpath, '//ol[@class="nexisresult"]//h2/a') == "FAILED":
        driver.back()
    return driver, result

def _get_caps(driver):
    '''
    Parses out caps-based key-value pairs in article txt provided by lexisnexis. 
    e.g.:

    PUBLICATION-TYPE: Zeitung
    '''
    valmap = {}
    for bold in driver.find_elements_by_xpath('//b'):
        if bold.text.strip()[-1]!=':': continue
        boldpos     = driver.page_source.find(bold.text)
        rest_source = driver.page_source[boldpos:]
        endpos      = rest_source.find("<br ")
        keylen      = len(bold.text+":</b>")
        val         = rest_source[keylen:endpos]
        valmap.update({bold.text:val})

    return valmap

# Go to main
def _go_to_main(driver):
    logger.debug("Resetting driver page position")
    driver.switch_to_default_content()
    driver.switch_to_frame('mainFrame')
    parents = driver.find_element('id','parentSet')
    driver.switch_to_frame(0)
    time.sleep(1)
    driver.switch_to_frame('powerFrame')
    time.sleep(1)
    driver.switch_to_frame(driver.find_element_by_xpath('.//frame[2]'))
    return driver

def get_countries_frame(driver):
    # go to alphabetical overview
    driver = _go_to_main(driver)
    time.sleep(1)
    driver.switch_to_frame(driver.find_element_by_xpath('.//frame[1]'))
    return driver

def go_to_alpha(driver):
    logger.info("Changing page to Alphabetic ordering of sources")
    driver = get_countries_frame(driver)
    driver.find_element('id','alpha').click()
    driver = _go_to_main(driver)
    time.sleep(1)

    return driver

def go_to_source_code(driver):
    driver = get_countries_frame(driver)
    driver.find_element('id','sourceCode').click()
    driver = _go_to_main(driver)
    time.sleep(1)
    return driver

def get_countries(driver, country=None):
    driver = _go_to_main(driver)
    driver = get_countries_frame(driver)

    countries = {o.text:o for o in driver.find_elements_by_xpath('.//select/option')}


    # country select
    if not country:
        driver = _go_to_main(driver)
        return countries

    if not country == "All Countries":
        try: countries[country].click()
        except: 
            driver.find_element('id','countryId').click()
            driver.find_element('id','countryId').send_keys(country)
            driver.find_element('id','countryId').send_keys(Keys.ENTER)
        driver = _go_to_main(driver)
        return driver, countries

    if country.capitalize() not in countries:
        driver = _go_to_main(driver)
        countrykeys = ', '.join(countries)
        raise Exception("Unknown country {country}. Pick one from {countries}")

    return driver, countries

def get_pages(driver):
    driver = get_countries_frame(driver)
    pages  = {p.text:p for p in driver.find_elements_by_xpath('//td[@class="srcseloption"]/a')}
    driver = _go_to_main(driver)
    return pages

def go_to_page(driver, pagename):
    driver = get_countries_frame(driver)
    for p in driver.find_elements_by_xpath('//td[@class="srcseloption"]/a'):
        if p.text == pagename:
            p.click()
            driver = _go_to_main(driver)
            return driver
    logger.warning("PAGE NOT FOUND")
    driver = _go_to_main(driver)
    return driver

def get_sources_frame(driver):
    driver.switch_to_frame(driver.find_element_by_xpath('.//frame[3]'))
    return driver

def get_sources(driver):
    driver  = get_sources_frame(driver)
    sources = {s.text : s.find_element_by_xpath('.//label').get_attribute('for') for s in driver.find_elements_by_xpath('//td[@class="SourceLink"]') if s}
    driver  = _go_to_main(driver)
    return sources

def select_source(driver, source):
    driver = get_sources_frame(driver)
    t      = source
    driver.find_element_by_xpath('//*[text()="%s"]' %t).click()
    driver = _go_to_main(driver)
    return driver

def paginate_sources(driver):
    driver   = get_sources_frame(driver)
    try:    nextpage = driver.find_element_by_xpath('//*[@title="View Next"]')
    except: nextpage = None
    if nextpage: nextpage.click()
    driver = _go_to_main(driver)
    return driver, nextpage!=None

def scan_pages_for_sources(driver):
    pages       = get_pages(driver)
    all_sources = get_sources(driver)
    
    change = True
    while change:
        all_sources.update(get_sources(driver))
        driver, change = paginate_sources(driver)

    for page in tqdm.tqdm(pages,disable=not VERBOSE):
        change = True
        driver = go_to_page(driver, page)
        while change:
            all_sources.update(get_sources(driver))
            driver, change = paginate_sources(driver)
    return all_sources

def start_spagetti_code():
    
    usage = "ln_parser.py [OPTIONS] QUERY"
    parser = optparse.OptionParser(usage=usage)

    parser.add_option('-c','--country', action='store', dest='country', help='Country to select sources or content from', default='All Countries')
    parser.add_option('-s','--sources', action='store', dest='sources', 
                        help='semi-colon seperated sources, e.g. "Die Welt; Der Spiegel"')
    parser.add_option('-r','--retries', action='store',      dest='retries', help='number of times to retry', default=1)
    parser.add_option('-d','--debug',   action='store_true', dest='debug',   help='set logging to debug')
    parser.add_option('-v','--verbose', action='store_true', dest='verbose', help='set logging to info')

    options, queryterms = parser.parse_args()

    if options.debug:
        logger.setLevel("DEBUG")
        VERBOSE = True
    elif options.verbose:
        logger.setLevel("INFO")
        VERBOSE = True
    else:
        logger.setLevel("WARN")
        VERBOSE = False
       
    if not options.sources:
        print("No sources specified, printing available sources for '%s':" %options.country)
        driver = _make_driver()
        sources = retry(int(options.retries), main, driver, country=options.country)
        for key in sources.keys():
            print(key)
    
    else:
        sources = [s.strip() for s in options.sources.split(';')]
        query   = ' OR '.join(queryterms)
        
        # report settings to user
        print("Searching for:\n\t'{query}'\n".format(**locals()))
        print("List of sources to consult:")
        for source in sources:
            print("- '{source}'".format(**locals()))
        if int(options.retries)==1:
            search_back_by_day(country=options.country, sources=sources, query=' OR '.join(queryterms))
        else:
            retry(int(options.retries), search_back_by_day, country=options.country, sources=sources, query=' OR '.join(queryterms))

if __name__ == '__main__':
    start_spagetti_code()
