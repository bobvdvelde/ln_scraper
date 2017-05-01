import sys
import re
import os.path
import glob
import time
from selenium import webdriver
import platform
import datetime
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

from IPython import embed


def make_driver(driver='Firefox', **kwargs):
    if driver == 'Firefox':
        drivername = 'geckodriver'
    elif driver == 'Opera':
        drivername = 'operadriver'

    ostype = platform.system()
    driverpath = "./{drivername}_{ostype}".format(**locals())
    kwargs.update({"executable_path": driverpath})
    wdriver = getattr(webdriver, driver)(**kwargs)

    return wdriver


def do_when_loaded(driver, condition, func, *args, **kwargs):
    retries = 10
    timeout = 30

    for i in range(retries):
        try:
            WebDriverWait(driver, timeout).until(EC.presence_of_element_located(condition))
            return func(*args, **kwargs)
        except TimeoutException:
            print(f'Timeout expired: {condition}, retrying {retries - i - 1} more times.')

    raise TimeoutException


def go_to_main(driver):
    driver.switch_to_default_content()

    do_when_loaded(driver, (By.ID, 'mainFrame'), driver.switch_to_frame, 'mainFrame')
    do_when_loaded(driver, (By.XPATH, './/frame[1]'),
                   lambda: driver.switch_to_frame(driver.find_element_by_xpath('.//frame[1]')))
    do_when_loaded(driver, (By.ID, 'powerFrame'), driver.switch_to_frame, 'powerFrame')

    do_when_loaded(driver, (By.XPATH, './/frame[2]'),
                   lambda: driver.switch_to_frame(driver.find_element_by_xpath('.//frame[2]')))
    return driver


def go_to_countries_frame(driver):
    driver = go_to_main(driver)
    do_when_loaded(driver, (By.XPATH, './/frame[3]'),
                   lambda: driver.switch_to_frame(driver.find_element_by_xpath('.//frame[1]')))
    return driver


def go_to_sources_frame(driver):
    driver = go_to_main(driver)
    do_when_loaded(driver, (By.XPATH, './/frame[3]'),
                   lambda: driver.switch_to_frame(driver.find_element_by_xpath('.//frame[3]')))
    return driver


def get_alphabet_button(driver):
    "Return the radio button that sorts alphabetically"
    driver = go_to_countries_frame(driver)
    alpha_btn = do_when_loaded(driver, (By.ID, 'alpha'),
                               driver.find_element_by_id, 'alpha')

    return alpha_btn


def get_country_button(driver, country):
    "Return the entry in the country dropdown box"
    driver = go_to_countries_frame(driver)
    country_xpath = f'.//select/option[text()="{country}"]'
    country_btn = do_when_loaded(driver, (By.XPATH, country_xpath),
                                 driver.find_element_by_xpath, country_xpath)
    return country_btn


def get_source_link(driver, name):
    "Return the clicable label that selects a source"
    for word in name.split():
        first_letter = word[0]
        driver = go_to_countries_frame(driver)
        button = [btn for btn in driver.find_elements_by_xpath('//a')
                  if btn.text == first_letter][0]
        button.click()

        driver = go_to_sources_frame(driver)
        source = [label for label in driver.find_elements_by_xpath('.//label')
                  if label.text == name]

        if len(source) > 0:
            return source[0]


def get_continue_button(driver):
    "Return the 'OK - Continue' button"
    driver = go_to_sources_frame(driver)
    btn = [elem for elem in driver.find_elements_by_xpath('.//img')
           if 'Continue' in elem.get_attribute('title')][0]

    return btn


def go_to_search_page(driver, name):
    # go to source page
    do_when_loaded(driver, (By.NAME, 'mainFrame'),
                   driver.switch_to_frame, 'mainFrame')
    el = do_when_loaded(driver, (By.LINK_TEXT, 'Sources'),
                        driver.find_element_by_link_text, 'Sources')

    el.click()

    # sort alphabetically
    alpha_btn = get_alphabet_button(driver)
    alpha_btn.click()

    # select only German sources
    country_btn = get_country_button(driver, 'Germany')
    country_btn.click()

    src = get_source_link(driver, name)
    src.click()
    c = get_continue_button(driver)
    c.click()


def wait_for_completion(driver):
    "Wait for the download to start and return the OK button"
    n_files = len(glob.glob(os.path.expanduser('~/Downloads/*.HTML')))

    # wait for the download to start
    do_when_loaded(driver, (By.CLASS_NAME, 'save-click'),
                   lambda: print('Download started'))

    return driver.find_element_by_xpath('(//img[@title="OK"])[2]')


def download(driver):
    driver.switch_to_default_content()
    do_when_loaded(driver, (By.ID, 'mainFrame'), driver.switch_to_frame, 'mainFrame')

    # get the number of documents
    count = do_when_loaded(driver, (By.ID, 'updateCountDiv'),
                           driver.find_element_by_id, 'updateCountDiv')
    n_documents = int(count.text[1:-1])
    print(n_documents)

    for start in range(1, n_documents + 1, 199):
        # set the document range
        end = min(n_documents, start + 199)
        print(f'Downloading documents {start}-{end}')

        # click the download button
        btn_xpath = '//a[@title="Download Delivery"]'
        btn = do_when_loaded(driver, (By.XPATH, btn_xpath),
                            driver.find_element_by_xpath, btn_xpath)
        btn.click()

        driver.switch_to_default_content()
        do_when_loaded(driver, (By.ID, 'mainFrame'), driver.switch_to_frame, 'mainFrame')

        rangebox = do_when_loaded(driver, (By.ID, 'rangetextbox'),
                                driver.find_element_by_id, 'rangetextbox')

        rangebox.click()
        rangebox.send_keys(f'{start}-{end}')

        # switch to the format options
        format_xpath = '//a[@href="#tabs-3"]'
        format_btn = do_when_loaded(driver, (By.XPATH, format_xpath),
                                    driver.find_element_by_xpath, format_xpath)
        format_btn.click()

        # set the format to HTML
        format_box = do_when_loaded(driver, (By.ID, 'delFmt'),
                                    driver.find_element_by_id, 'delFmt')
        format_box.click()
        format_box.send_keys('H')
        format_box.click()

        # click the download button
        download_xpath = '//img[@title="Download"]'
        download_btn = do_when_loaded(driver, (By.XPATH, download_xpath),
                                    driver.find_element_by_xpath, download_xpath)
        download_btn.click()

        # wait for the download to start and dismiss the popup
        ok_btn = wait_for_completion(driver)
        ok_btn.click()

    # wait for the last remaining downloads
    time.sleep(2)


def search(driver, query, start_date, end_date):
    # input the query
    do_when_loaded(driver, (By.ID, 'mainFrame'), driver.switch_to_frame, 'mainFrame')
    textarea = do_when_loaded(driver, (By.ID, 'terms'),
                              driver.find_element_by_id, 'terms')
    textarea.send_keys(query)

    # set the date
    dropdown = do_when_loaded(driver, (By.ID, 'dateSelector1'),
                              driver.find_element_by_id, 'dateSelector1')
    dropdown.click()
    dropdown.send_keys('Date is bet')

    fromdate = do_when_loaded(driver, (By.ID, 'fromDate1'),
                              driver.find_element_by_id, 'fromDate1')
    fromdate.click()
    fromdate.clear()
    fromdate.send_keys(start_date.strftime('%d/%m/%Y'))

    todate = do_when_loaded(driver, (By.ID, 'toDate1'),
                            driver.find_element_by_id, 'toDate1')
    todate.click()
    todate.clear()
    todate.send_keys(end_date.strftime('%d/%m/%Y'))

    # click the submit button
    submit_xpath = '//*[@type="submit"]'
    submit_btn = do_when_loaded(driver, (By.XPATH, submit_xpath),
                                driver.find_element_by_xpath, submit_xpath)
    submit_btn.click()


def main():
    # TODO: better argument handling
    query = ' '.join(sys.argv[1:])
    paper = 'Die Welt'

    end_date = datetime.date.today()
    range_delta = datetime.timedelta(days=100)
    offset_delta = datetime.timedelta(days=101)

    while end_date.year > 2014:
        try:
            start_date = end_date - range_delta

            print('Downloading from {} to {}'.format(
                start_date.strftime('%d/%m/%Y'), end_date.strftime('%d/%m/%Y')))

            driver = make_driver('Opera')
            driver.get('http://academic.lexisnexis.nl')
            go_to_search_page(driver, paper)
            search(driver, query, start_date, end_date)
            download(driver)
            driver.close()
        except Exception as e:
            print(e)

        end_date -= offset_delta


if __name__ == '__main__':
    main()
