from listscraper.utility_functions import val2stars, stars2val
from bs4 import BeautifulSoup
from tqdm import tqdm
import requests
import numpy as np
import re

_domain = 'https://letterboxd.com/'

def scrape_list(list_url, page_options, output_file_extension, list_type, quiet=False, concat=False):
    """
    Scrapes a Letterboxd list or diary. Takes into account any optional page selection.
    """

    list_films = []

    # Handle diary scraping directly
    if list_type == "diary":
        print("📘 Scraping a diary...")
        list_films = scrape_diary(list_url, page_options, output_file_extension, quiet, concat)
    else:
        print("🎞️ Scraping a list...")
        # Scrape all or selected pages
        if (page_options == []) or (page_options == "*"):
            while True:
                page_films, page_soup = scrape_page(list_url, list_url, output_file_extension, list_type, quiet, concat)
                list_films.extend(page_films)

                # Check if there is another page
                next_button = page_soup.find('a', class_='next')
                if next_button is None:
                    break
                list_url = _domain + next_button['href']
        else:
            for p in page_options:
                new_link = list_url + f"page/{p}/"
                try:
                    page_films, page_soup = scrape_page(new_link, list_url, output_file_extension, list_type, quiet, concat)
                    list_films.extend(page_films)
                except Exception as e:
                    print(f"        No films on page {p}... ({e})")
                    continue    

    # Write results out
    import csv, os
    os.makedirs("scraper_outputs", exist_ok=True)

    if list_films:
        out_path = os.path.join("scraper_outputs", f"{list_type}_output.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list_films[0].keys())
            writer.writeheader()
            writer.writerows(list_films)
        print(f"✅ Saved {len(list_films)} entries to {out_path}")
    else:
        print("⚠️ No entries found — nothing saved.")

    return list_films



def scrape_page(list_url, og_list_url, output_file_extension, list_type, quiet=False, concat=False):
    """
    Scrapes a single Letterboxd list page and extracts all film entries.
    """
    import requests, numpy as np
    from bs4 import BeautifulSoup
    from tqdm import tqdm
    from .scrape_functions import scrape_film  # ensure local import

    page_films = []
    response = requests.get(list_url, headers={'User-Agent': 'Mozilla/5.0'})
    if response.status_code != 200:
        print(f"Error loading {list_url} ({response.status_code})")
        return [], None

    soup = BeautifulSoup(response.content, 'lxml')

    # Updated HTML selectors to support new Letterboxd layout
    table = (
        soup.find('ul', class_='poster-list')
        or soup.find('ul', class_='list-entries')
        or soup.find('section', class_='poster-list')
    )
    if table is None:
        print(f"⚠️  No film list found on {list_url}")
        return [], soup

    films = table.find_all('li')
    if not films:
        print(f"⚠️  Found no <li> entries in {list_url}")
        return [], soup

    not_found = np.nan if output_file_extension == ".csv" else None

    for film in tqdm(films, disable=quiet):
        try:
            film_dict = scrape_film(film, not_found)
            if concat:
                film_dict["List_URL"] = og_list_url
            page_films.append(film_dict)
        except Exception as e:
            print(f"Error parsing film entry: {e}")
            continue

    return page_films, soup


        
def scrape_film(film_html, not_found):
    """
    Scrapes all available information regarding a film. 
    The function makes multiple request calls to relevant Letterboxd film URLs and gets their raw HTML code.
    Using manual text extraction, the wanted information is found and stored in a dictionary.
    
    Parameters:
        film_html (str):    The raw <li> HTML string of the film object obtained from the list page HTML.
        not_found (object): Either 'np.nan' if output is CSV or 'None' if output is JSON
    Returns:
        film_dict (dict):   A dictionary containing all the film's information.
    """
    
    film_dict = {}

    # Obtaining release year, director and average rating of the movie
    film_card = film_html.find('div').get('data-target-link')[1:]
    film_url = _domain + film_card
    filmget = requests.get(film_url)
    film_soup = BeautifulSoup(filmget.content, 'html.parser')

    # Finding the film name
    film_dict["Film_title"] = film_soup.find("div", {"class" : "col-17"}).find("h1").text
    
    # Try to find release year, handle cases where it's missing
    try:
        release_years = film_soup.find_all('div', class_='releaseyear')
        if len(release_years) > 1:  # Check if we have enough elements
            year_text = release_years[1].find('a').text.strip()
            release_year = int(year_text) if year_text else 0
        else:
            release_year = 0
    except (AttributeError, IndexError, ValueError):
        release_year = 0
        
    film_dict["Release_year"] = not_found if release_year == 0 else release_year

    # Try to find director, if missing insert nan
    director = film_soup.find('meta', attrs={'name':'twitter:data1'}).attrs['content']
    if director == "":
        director = not_found
    film_dict["Director"] = director

    # Finding the cast, if not found insert a nan
    try:
        cast = [ line.contents[0] for line in film_soup.find('div', attrs={'id':'tab-cast'}).find_all('a')]

        # remove all the 'Show All...' tags if they are present
        film_dict["Cast"] = [i for i in cast if i != 'Show All…']
    except:
        film_dict["Cast"] = not_found

    # Finding average rating, if not found insert a nan
    try:
        film_dict["Average_rating"] = float(film_soup.find('meta', attrs={'name':'twitter:data2'}).attrs['content'][:4])
    except:
        film_dict["Average_rating"] = not_found

    # Try to find the list owner's rating of a film if possible and converting to float
    try:
        stringval = film_html.attrs['data-owner-rating']
        if stringval != '0':
            film_dict["Owner_rating"] = float(int(stringval)/2)
        else:
            film_dict["Owner_rating"] = not_found
    except:
        # Extra clause for type 'film' lists
        try:
            starval = film_html.find_all("span")[-1].text
            film_dict["Owner_rating"] = stars2val(starval, not_found)
        except:
            film_dict["Owner_rating"] = not_found
        
    # Finding film's genres, if not found insert nan
    try: 
        genres = film_soup.find('div', {'class': 'text-sluglist capitalize'})
        film_dict["Genres"] = [genres.text for genres in genres.find_all('a', {'class': 'text-slug'})]
    except:
        film_dict["Genres"] = not_found

    # Get movie runtime by searching for first sequence of digits in the p element with the runtime, if not found insert nan
    try: 
        film_dict["Runtime"] = int(re.search(r'\d+', film_soup.find('p', {'class': 'text-link text-footer'}).text).group())
    except:
        film_dict["Runtime"] = not_found

    # Finding countries
    try:
        film_dict["Countries"] = [ line.contents[0] for line in film_soup.find('div', attrs={'id':'tab-details'}).find_all('a', href=re.compile(r'country'))]
        if film_dict["Countries"] == []:
            film_dict["Countries"] = not_found
    except:
        film_dict["Countries"] = not_found

    # Finding spoken and original languages
    try:
        # Replace non-breaking spaces (\xa0) by a normal space 
        languages = [ line.contents[0].replace('\xa0', ' ') for line in film_soup.find('div', attrs={'id':'tab-details'}).find_all('a', href=re.compile(r'language'))]
        film_dict["Original_language"] = languages[0]                                      # original language (always first)
        film_dict["Spoken_languages"] = list(sorted(set(languages), key=languages.index))   # all unique spoken languages
    except:
        film_dict["Original_language"] = not_found
        film_dict["Spoken_languages"] = not_found

    # Finding the description, if not found insert a nan
    try:
        film_dict['Description'] = film_soup.find('meta', attrs={'name' : 'description'}).attrs['content']
    except:
        film_dict['Description'] = not_found

    # !! Currently not working with films that have a comma in their title
    # # Finding alternative titles
    # try:
    #     alternative_titles = film_soup.find('div', attrs={'id':'tab-details'}).find('div', class_="text-indentedlist").text.strip().split(", ")
    # except:
    #     alternative_titles = not_found

    # Finding studios
    try:
        film_dict["Studios"] = [ line.contents[0] for line in film_soup.find('div', attrs={'id':'tab-details'}).find_all('a', href=re.compile(r'studio'))]
        if film_dict["Studios"] == []:
            film_dict["Studios"] = not_found
    except:
        film_dict["Studios"] = not_found

    # Getting number of watches, appearances in lists and number of likes (requires new link) ## 
    movie = film_url.split('/')[-2]                                        # Movie title in URL
    r = requests.get(f'https://letterboxd.com/csi/film/{movie}/stats/')    # Stats page of said movie
    stats_soup = BeautifulSoup(r.content, 'lxml')

    # Get number of people that have watched the movie
    watches = stats_soup.find('a', {'class': 'has-icon icon-watched icon-16 tooltip'})["title"]
    watches = re.findall(r'\d+', watches)    # Find the number from string
    film_dict["Watches"] = int(''.join(watches))          # Filter out commas from large numbers

    # Get number of film appearances in lists
    list_appearances = stats_soup.find('a', {'class': 'has-icon icon-list icon-16 tooltip'})["title"]
    list_appearances = re.findall(r'\d+', list_appearances) 
    film_dict["List_appearances"] = int(''.join(list_appearances))

    # Get number of people that have liked the movie
    likes = stats_soup.find('a', {'class': 'has-icon icon-like icon-liked icon-16 tooltip'})["title"]
    likes = re.findall(r'\d+', likes)
    film_dict["Likes"] = int(''.join(likes))

    # Getting info on rating histogram (requires new link)
    r = requests.get(f'https://letterboxd.com/csi/film/{movie}/rating-histogram/')    # Rating histogram page of said movie
    hist_soup = BeautifulSoup(r.content, 'lxml')

    # Get number of fans. Amount is given in 'K' notation, so if relevant rounded off to full thousands
    try:
        fans = hist_soup.find('a', {'class': 'all-link more-link'}).text
        fans = re.findall(r'\d+.\d+K?|\d+K?', fans)[0]
        if "." and "K" in fans:
            fans = int(float(fans[:-1]) * 1000)
        elif "K" in fans:
            fans = int(fans[-1]) * 1000
        else:
            fans = int(fans)
    except:
        fans = 0
    film_dict["Fans"] = fans

    # Get rating histogram (i.e. how many star ratings were given) and total ratings (sum of rating histogram)
    ratings = hist_soup.find_all("li", {'class': 'rating-histogram-bar'})
    tot_ratings = 0
    if len(ratings) != 0:
        for i, r in enumerate(ratings):
            string = r.text.strip(" ")
            stars = val2stars((i+1)/2, not_found)
            if string == "":
                film_dict[f"{stars}"] = 0
            else:
                Nratings = re.findall(r'\d+', string)[:-1]
                Nratings = int(''.join(Nratings))
                film_dict[f"{stars}"] = Nratings
                tot_ratings += Nratings

    # If the film has not been released yet (i.e. no ratings)
    else:
        for i in range(10):
            stars = val2stars((i+1)/2, not_found)
            film_dict[f"{stars}"] = 0
            
    film_dict["Total_ratings"] = tot_ratings

    # Thumbnail URL?

    # Banner URL?
    
    # Save the film URL as an extra column
    film_dict["Film_URL"] = film_url
    
    return film_dict

def scrape_diary(base_url, page_options, output_file_extension, quiet, concat):
    """
    Scrapes diary entries for a user.
    Returns a list of dicts with keys like: date, film_title, year, rating, review, tags, url, director, etc.
    """

    session = requests.Session()
    films = []

    # Letterboxd diary pages are paginated. We'll try to detect pages to fetch.
    # Default: page 1 only if user didn't request more. Support page_options same as other scrapers.
    # For simplicity, if page_options == [] => scrape all pages (dangerous); else iterate requested pages.
    if page_options == []:
        pages_to_scrape = [1]   # keep conservative by default; change to '*' logic if you want all pages
    else:
        pages_to_scrape = page_options

    for page in pages_to_scrape:
        # build diary page url for a given page number:
        # common diary style: https://letterboxd.com/username/films/diary/page/2/
        if base_url.rstrip('/').endswith('diary'):
            page_url = base_url.rstrip('/') + f'/page/{page}/'
        else:
            # handle /username/diary/ style
            page_url = base_url.rstrip('/') + f'/page/{page}/'

        resp = session.get(page_url, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code != 200:
            print(f"        Warning: page {page} returned status {resp.status_code}")
            continue

        soup = BeautifulSoup(resp.text, 'lxml')

        # Try several candidate selectors for diary entries:
        entry_selectors = [
            "li.diary-entry",            # common candidate
            "div.diary-entry",           # alternate
            "article.diary-entry",       # alternate
            "li.entry"                   # fallback
        ]

        entries = []
        for sel in entry_selectors:
            entries = soup.select(sel)
            if entries:
                break

        if not entries:
            # nothing found — try to find article tags with a date or 'diary' in class
            entries = soup.find_all('article')
            if not entries:
                print(f"        No diary entries found on page {page} (tried selectors).")
                continue

        for e in entries:
            try:
                # Extract date (if present)
                date_tag = e.find(attrs={"class": lambda x: x and "entry-dates" in x}) \
                           or e.find('time') \
                           or e.find('span', {'class':'date'})
                date = date_tag.get_text(strip=True) if date_tag else ""

                # Extract film title & link
                # common pattern: <a class="film-title" href="/film/film-slug/">
                film_link = e.find('a', href=True)
                film_title = film_link.get_text(strip=True) if film_link else ""
                film_url = f"https://letterboxd.com{film_link['href']}" if film_link else ""

                # Extract year if present (sometimes in title or separate)
                year_tag = e.find('small', {'class': 'year'}) or e.find('span', {'class':'film-year'})
                year = year_tag.get_text(strip=True).strip('()') if year_tag else ""

                # Extract rating (stars)
                rating_tag = e.select_one(".rating, .film-rating, .diary-rating")
                rating = None
                if rating_tag:
                    # rating may be encoded as 'data-rating' or stars text
                    if rating_tag.has_attr('data-rating'):
                        rating = float(rating_tag['data-rating'])
                    else:
                        rating_text = rating_tag.get_text(strip=True)
                        # attempt simple numeric parse
                        try:
                            rating = float(rating_text)
                        except:
                            rating = rating_text

                # Extract short review text
                review_tag = e.select_one('p')
                review = review_tag.get_text(strip=True) if review_tag else ""

                # Collect director/name by following film_url if we need more details
                director = ""
                # optional: fetch film page to extract director (costly)

                films.append({
                    "date": date,
                    "film_title": film_title,
                    "year": year,
                    "rating": rating,
                    "review": review,
                    "film_url": film_url,
                    "director": director,
                })
            except Exception as exc:
                # non-fatal: keep going
                print(f"        Warning parsing an entry: {exc}")
                continue

        # be polite
        time.sleep(0.25)

    if not films:
        # return a single entry to preserve header structure as your other scrapers do
        return [{"note": "no diary entries found"}]
    return films
