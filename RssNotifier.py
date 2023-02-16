#!/usr/bin/python3
import sqlite3
import smtplib
import feedparser
import argparse
import os
import requests
from email.mime.text import MIMEText
from lxml import etree
from urllib.parse import urlparse, urlunparse


db_dir = os.path.dirname(__file__)
db_path = os.path.join(db_dir, 'rss.db')
db_connection = sqlite3.connect(db_path)
db = db_connection.cursor()
db.execute('CREATE TABLE IF NOT EXISTS feed (name TEXT, url TEXT, type TEXT, rule TEXT)')
db.execute('CREATE TABLE IF NOT EXISTS article (title TEXT, link TEXT, date TEXT)')
db.execute('CREATE TABLE IF NOT EXISTS smtp (server TEXT, port TEXT, username TEXT, password TEXT, receiver TEXT)')


def getparser():
    """ 获取命令行的参数 """
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    add_cmd = subparsers.add_parser('add', help='Add RSS feed')
    add_cmd.add_argument('--name', type=str, help='RSS feed name')
    add_cmd.add_argument('--url', type=str, help='RSS feed url')
    add_cmd.add_argument('--type', type=str, help='RSS feed type')
    add_cmd.add_argument('--rule', type=str, help='RSS feed rule')
    add_cmd.set_defaults(func=add_rss_feed)
    read_cmd = subparsers.add_parser('read', help='Read RSS feed')
    read_cmd.set_defaults(func=read_article_feed)
    config_cmd = subparsers.add_parser('config', help='Config SMTP server')
    config_cmd.add_argument('--server', type=str, help='SMTP server address')
    config_cmd.add_argument('--port', type=str, help='SMTP server port')
    config_cmd.add_argument('--username', type=str, help='E-mail address')
    config_cmd.add_argument('--password', type=str, help='E-mail password')
    config_cmd.add_argument('--receiver', type=str, help='Receiver E-mail address')
    config_cmd.set_defaults(func=config_smtp_server)
    return parser


def add_rss_feed(args):
    """ 添加源 """
    db.execute("INSERT INTO feed VALUES (?, ?, ?, ?)", (args.name, args.url, args.type, args.rule))
    db_connection.commit()


def read_article_feed(args):
    """ 读取文章 """
    db.execute("SELECT url, type, rule FROM feed")
    feed_list = db.fetchall()
    for feed in feed_list:
        if feed[1] == 'html':
            get_article(feed[0], feed[2])
        if (feed[1] == 'atom' or feed[1] == 'rss'):
            feed = feedparser.parse(feed[0])
            for article in feed['entries']:
                if article_is_not_db(article['title'], article['link'], article['published']):
                    send_notification(article['title'], article['link'])
                    add_article_to_db(article['title'], article['link'], article['published'])


def config_smtp_server(args):
    """ 配置SMTP服务 """
    db.execute("INSERT INTO smtp VALUES (?, ?, ?, ?, ?)", (args.server, args.port, args.username, args.password, args.receiver))
    db_connection.commit()


def get_article(feed, rule):
    """ 获取文章
    参数：
        feed (str)：源地址
        rule (str)：规则
    """
    response = requests.get(feed)
    response.encoding = response.apparent_encoding
    html = etree.HTML(response.text)
    article = html.xpath(rule)
    url = html.xpath(rule + '/@href')
    i = 0
    for title in article:
        url_parse_result = urlparse(url[i])
        if (url_parse_result.scheme == '' and url_parse_result.netloc == ''):
            feed_parse_result = urlparse(feed)
            article_link = urlunparse([feed_parse_result.scheme, feed_parse_result.netloc, url[i], '', '', ''])
            if article_is_not_db(title.text, article_link, ''):
                send_notification(title.text, article_link)
                add_article_to_db(title.text, article_link, '')
        else:
            if article_is_not_db(title.text, url[i], ''):
                send_notification(title.text, url[i])
                add_article_to_db(title.text, url[i], '')
        i = i + 1


def article_is_not_db(article_title, article_link, article_date):
    """ 检查文章是否在数据库中
    参数：
        article_title (str)：文章标题
        article_link  (str)：文章链接
        article_date  (str)：文章发布日期
    返回值：
        数据库不存在文章返回True
        数据库已存在文章返回False
    """
    db.execute("SELECT * FROM article WHERE title=? AND link=? AND date=?", (article_title, article_link, article_date))
    if not db.fetchall():
        return True
    else:
        return False


def send_notification(article_title, article_url):
    """ 发送邮件提醒
    参数：
        article_title (str)：文章标题
        article_url   (str)：文章链接
    """

    db.execute("SELECT server, port, username, password, receiver FROM smtp")
    smtp_info = db.fetchall()
    smtp_server = smtplib.SMTP(smtp_info[0][0], smtp_info[0][1])
    smtp_server.ehlo()
    smtp_server.starttls()
    smtp_server.login(smtp_info[0][2], smtp_info[0][3])
    msg = MIMEText(f'{article_url}')
    msg['Subject'] = '【RSS订阅】' + article_title
    msg['From'] = 'yangerald@163.com'
    msg['To'] = smtp_info[0][4]
    smtp_server.send_message(msg)
    smtp_server.quit()
    print(article_title + '（' + article_url + '）')


def add_article_to_db(article_title, article_link, article_date):
    """ 添加文章到数据库
    参数：
        article_title (str)：文章标题
        article_link  (str)：文章链接
        article_date  (str)：文章发布日期
    """
    db.execute("INSERT INTO article VALUES (?, ?, ?)", (article_title, article_link, article_date))
    db_connection.commit()


if __name__ == '__main__':
    parser = getparser()
    args = parser.parse_args()
    try:
        args.func(args)
    except AttributeError:
        parser.print_help()
        parser.exit()
    db_connection.close()