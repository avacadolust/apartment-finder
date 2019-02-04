from craigslist import CraigslistHousing
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean
from sqlalchemy.orm import sessionmaker
from dateutil.parser import parse
from util import post_listing_to_slack, find_points_of_interest
from slackclient import SlackClient
import time
import settings
from pprint import pprint
#%load_ext autoreload
#%autoreload 2

settings.BOXES = {

 'mid_city':[[34.041998,-118.334176],[34.105833,-118.245768]]

 #'hollywood' : [[34.083433,-118.34178],[34.118561,-118.292153]],

 #'east_of_hollywood':[[34.083798,-118.291904],[34.118925,-118.242277]],

 #'north_east_of_downtown':[[34.047509,-118.296107],[34.08394, -118.24648]]
                            
        }

engine = create_engine('sqlite:///listings.db', echo=False)

Base = declarative_base()

class Listing(Base):
    """
    A table to store data on craigslist listings.
    """

    __tablename__ = 'listings'

    id = Column(Integer, primary_key=True)
    link = Column(String, unique=True)
    created = Column(DateTime)
    geotag = Column(String)
    lat = Column(Float)
    lon = Column(Float)
    name = Column(String)
    price = Column(Float)
    location = Column(String)
    cl_id = Column(Integer, unique=True)
    area = Column(String)
    bart_stop = Column(String)

Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()


def do_scrape(area):
    cl_h = CraigslistHousing(site=settings.CRAIGSLIST_SITE, area=area, category=settings.CRAIGSLIST_HOUSING_SECTION,
                         filters={'max_price': settings.MAX_PRICE, "min_price": settings.MIN_PRICE})
    results = []
    gen = cl_h.get_results(sort_by='newest', geotagged=True, limit=40)
    while True:
        try:
            result = next(gen)
        except StopIteration:
            break
        except Exception:
            continue
        listing = session.query(Listing).filter_by(cl_id=result["id"]).first()

        # Don't store the listing if it already exists.
        if listing is None:
            lat = 0
            lon = 0
            if result["geotag"] is not None:
                # Assign the coordinates.
                lat = result["geotag"][0]
                lon = result["geotag"][1]

                # Annotate the result with information about the area it's in and points of interest near it.
                geo_data = find_points_of_interest(result["geotag"], result["where"])
                result.update(geo_data)
            else:
                result["area"] = ""
                result["bart"] = ""

            # Try parsing the price.
            price = 0
            try:
                price = float(result["price"].replace("$", ""))
            except Exception:
                pass

            # Create the listing object.
            listing = Listing(
                link=result["url"],
                created=parse(result["datetime"]),
                lat=lat,
                lon=lon,
                name=result["name"],
                price=price,
                location=result["where"],
                cl_id=result["id"],
                area=result["area"],
                bart_stop=result["bart"]
            )

            # Save the listing so we don't grab it again.
            session.add(listing)
            session.commit()

            # Return the result if it's near a bart station, or if it is in an area we defined.
            if len(result["area"]) > 0:
                results.append(result)
    return results

def main():
    sc = SlackClient(settings.SLACK_TOKEN)
    for area in settings.AREAS:
        results = do_scrape(area)
        for result in results:
            post_listing_to_slack(sc,result)