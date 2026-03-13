import feedparser
import httpx
import os
import django

from apps.models import Article, ArticleImage, Summary

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from bs4 import BeautifulSoup


def extract_image(article, entry):
    if article.source == "Gazeta":
        return entry['links'][1]['href']
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }
    response = httpx.get(article.url, headers=headers, follow_redirects=True)
    soup = BeautifulSoup(response.text, "html.parser")
    return soup.find_all("img")[10]['src']


def save_image(image_url, article):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }
    if image_url:
        try:
            response = httpx.get(image_url, headers=headers, follow_redirects=True, timeout=20)
            response.raise_for_status()
        except httpx.ConnectTimeout:
            print("⏳ Timeout:", image_url)
            return

        except Exception as e:
            print("❌ Fetch failed:", image_url, e)
            return
        img = ArticleImage(image=response.content, article=article)
        img.save()


rss = [
    "https://www.gazeta.uz/oz/rss/",
    "https://kun.uz/news/rss",
]


def crawl_with_rss(owner):
    for url in rss:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if not Article.objects.filter(owner=owner, url=entry['link']).exists():
                article = Article.objects.create(owner=owner, title=entry['title'], content=entry['summary'], is_summary=True,
                                                 url=entry['link'], source=feed.feed.title,
                                                 published_date=entry['published'])
                image_url = extract_image(article=article, entry=entry)
                save_image(image_url=image_url, article=article)
                Summary.objects.create(article=article, summary_text=entry['summary'])
        print(f"{feed.feed.title} dan barcha ma'lumotlar yuklandi!")


http_rss = [
    "http://www.independent.co.uk/news/uk/rss",
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://abcnews.go.com/abcnews/internationalheadlines",
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
]


def extract_image_from_independent(article):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }
    response = httpx.get(article.url, headers=headers, follow_redirects=True)
    soup = BeautifulSoup(response.text, "html.parser")
    images = soup.find_all("img")
    if images:
        if article.source == 'Transport Topics':
            image_url = "https://www.ttnews.com" + images[1]['src']
            save_image(image_url=image_url, article=article)
        elif article.source == 'Truck News' and images[2]['src']:
            save_image(image_url=images[2]['src'], article=article)
        else:
            save_image(image_url=images[1]['src'], article=article)


def crawl_from_rss_http(owner):
    for url in http_rss:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            link = entry['link']
            title = entry['title']
            content = entry['summary']
            source = feed.feed.title
            published = entry['published']

            if url == "http://www.independent.co.uk/news/uk/rss":
                body = ""
                for letter in content:
                    if letter not in ["<", ">", "p", "/"]:
                        body += letter
                content = body

            if not Article.objects.filter(owner=owner, url=link).exists():
                article = Article.objects.create(owner=owner, title=title, content=content, is_summary=False,
                                                 url=link, source=source, published_date=published)
                extract_image_from_independent(article=article)

        print(f"{feed.feed.title} dan barcha ma'lumotlar yuklandi!")


def image_from_qalampir(article):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }
    response = httpx.get(article.url, headers=headers, follow_redirects=True)
    soup = BeautifulSoup(response.text, "html.parser")
    images = soup.find_all("img")[1]['src']
    if images:
        save_image(image_url=images, article=article)


def crawl_from_qalampir(owner):
    response = httpx.get("https://qalampir.uz/uz/latest")
    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.find_all("a", {"class": "news-card"})

    for card in cards:
        url = "https://qalampir.uz" + card.get("href")
        if not Article.objects.filter(owner=owner, url=url).exists():
            title = card.find("p", {"class": "news-card-content-text"}).text.strip()
            published = card.find("span", {"class": "date"}).text
            response = BeautifulSoup(httpx.get(url).text, "html.parser").find_all("div", {"class": "col-12"})
            content = response[4].find("p").text.strip()
            article = Article.objects.create(owner=owner, title=title, url=url, published_date=published,
                                             content=content, is_summary=True, source='qalampir.uz')
            image_from_qalampir(article=article)
    print("Qalampir dan barcha ma'lumotlar yuklandi")


def crawl_from_sputnik():
    response = httpx.get("https://oz.sputniknews.uz/news/")
    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.find_all("div", {"class": "list__item"})
    for card in cards:
        url = "https://oz.sputniknews.uz" + card.find("a", {"class": "list__title"}).get("href")
        if not Article.objects.filter(url=url).exists():
            title = card.find("a", {"class": "list__title"}).text
            article_response = httpx.get(url)
            soup1 = BeautifulSoup(article_response.text, "html.parser")
            published = soup1.find("div", {"class": "article__info-date"}).text
            content = "".join(p.text for p in soup1.find_all("div", {"class": "article__text"}))
            article = Article.objects.create(url=url, content=content, published_date=published, title=title,
                                             source="sputniknews.uz", is_summary=False)
    print("Sputnik dan barcha ma'lumotlar yuklandi")


def crawl_from_guardian(owner):
    response = httpx.get("https://www.theguardian.com/world")
    soup = BeautifulSoup(response.text, "html.parser")
    links = soup.find_all("a", {"class": "dcr-2yd10d"})

    for link in links:
        url = 'https://www.theguardian.com' + link.get('href')
        if not Article.objects.filter(owner=owner, url=url).exists():
            title = link.get("aria-label")
            response2 = httpx.get(url)
            soup2 = BeautifulSoup(response2.text, "html.parser")
            published_date = None
            content = "".join(p.text for p in soup2.find_all("p", {"class": "dcr-130mj7b"}))
            article = Article.objects.create(
                owner=owner,
                content=content,
                url=url,
                title=title,
                published_date=published_date,
                source="theguardian.com",
                is_summary=False
            )
    print("Guardian dan barcha ma'lumotlar yuklandi")


def crawl_from_truck(owner):
    print("here comes!")
    rss_truck_list = [
        "http://www.ttnews.com/rss.xml",
        "https://www.trucknews.com/rss/"
    ]
    for url in rss_truck_list:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            link = entry['link']
            title = entry['title']
            content = entry['summary']
            source = feed.feed.title
            published = entry['published']

            if not Article.objects.filter(url=link, owner=owner).exists():
                article = Article.objects.create(owner=owner, title=title, content=content, is_summary=False,
                                                 url=link, source=source, published_date=published)
                extract_image_from_independent(article=article)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }
    response = httpx.get("https://www.freightwaves.com/news/category/trucking", headers=headers, follow_redirects=True)
    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.find_all("article")
    for card in cards:
        link = card.find("a")['href']
        title = card.find("h2").text.strip()
        content = card.find("p").text
        published = card.find("span").text.strip()
        image_link = card.find("img")['src']
        if not Article.objects.filter(url=link, owner=owner).exists():
            article = Article.objects.create(owner=owner, title=title, content=content, is_summary=False,
                                             url=link, source="freightwaves.com", published_date=published)
            save_image(article=article, image_url=image_link)
