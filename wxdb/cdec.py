"""
Interact with California Data Exchange Center (CDEC) to get metadata and timeseries data
"""

import logging
import pandas as pd
from datetime import datetime
import pytz
import grequests
import requests
import json

__author__ = "Scott Havens"
__maintainer__ = "Scott Havens"
__email__ = "scott.havens@ars.usda.gov"
__date__ = "2017-08-03"

logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

class CDEC():
    """
    CDEC class to interact with the CDEC website.
    
    Args:
        db: :class:`~wxcb.database.Database` instance to use for inserting data
        config: the `[mesoset_*]` section of the config file. These are parameters
            for the Mesowest API and will get passed directly to Mesowest.
    """
        
    conversion = {
        'LATITUDE': 'latitude',
        'STATION_ID': 'primary_id',
        'LONGITUDE': 'longitude',
        'STATION_NAME': 'station_name',
        'ELEVATION': 'elevation',
        'AGENCY_NAME': 'primary_provider'
        }
        
    metadata_table = 'tbl_metadata'
    
    station_info_url = 'http://cdec.water.ca.gov/cdecstation2/CDecServlet/getStationInfo'
    
    def __init__(self, db):
        self._logger = logging.getLogger(__name__)
        
        self.db = db
        
        self._logger.debug('Initialized CDEC')
        
        
    def single_station_info(self, stid):
        """
        Query the station info, returns the sensor information as well
        
        Args:
            stid: a single station ID's to fetch
        
        Returns:
            Dataframe for station that will have all the sensors names, and 
            timescale 
        """
        r = requests.get('http://cdec.water.ca.gov/cdecstation2/CDecServlet/getStationInfo',
                         params={'stationID': stid})
        data = json.loads(r.text)
        
        return pd.DataFrame(data['STATION'])
    

    def multi_station_info(self, stids, fields=False):
        """
        Query the station info for a list of stations. Because of the many
        small requests, use async grequests to request all at once.
        
        Args:
            stids: list of station ID's to fetch
            fields: True to return all data or False to return the first record
            
        Returns:
            DataFrame of the station info
        """
        
        # build the requests
        r = []
        for s in stids:
            r.append(grequests.get(self.station_info_url, params={'stationID': s}))
            
        # Because the CDEC site sucks, we have to really thottle the number of 
        # concurrent requests...
        res = grequests.map(r, size=1)
        
        # go through the responses and parse
        df = []
        for rs in res:
            if rs:
                if rs.status_code == 200:
                    try:
                        data = json.loads(rs.text)
                        d = pd.DataFrame(data['STATION'])
                        if fields:
                            df.append(d)
                        else:
                            df.append(d.iloc[0])
                        self._logger.debug('Got metadata for {}'.format(d['STATION_ID'][0]))
                    except Exception:
                        pass
#                         self._logger.debug('Metadata problem for {} - {}'.format(d['STATION_ID'][0], e))
                        
        
        return pd.concat(df, axis=1).T.reset_index()
        
    def metadata(self):
        """
        Retrieve the metadata from Mesowest. Two calls are made to the Mesowest API.
        The first call is to get the networks in order to determine the `network` and
        `primary_provider`. The second call retrieves the metadata given the `config`
        parameters. The two dataframes are combined and inserted into the database
        given the :class:`~wxcb.database.Database` instance.
        """
        
        self._logger.info('Obtaining metadata form CDEC')
                
        # this JSON file only has all the station names     
#         r = urllib.request.urlopen('http://cdec.water.ca.gov/cdecstation2/CDecServlet/getAllStations')
#         data = json.loads(r.read().decode(r.info().get_param('charset') or 'utf-8'))
        
        r = requests.get('http://cdec.water.ca.gov/cdecstation2/CDecServlet/getAllStations')
        data = json.loads(r.text)
        df = pd.DataFrame(data['STATION'])
        
        # request the data for all stations
        info = self.multi_station_info(df['STATION_ID'])
        
        # merge the dataframes, not needed since info has everything
#         d = pd.merge(df['STATION_ID'].to_frame(), info, on='STATION_ID')
                          
        # pull out the data from CDEC into the database format
        DF = pd.DataFrame()
        for c in self.conversion:
            DF[self.conversion[c]] = info[c]

        # these are the reported lat/long's for the station that may get changed
        # down the road due to location errors
        DF['reported_lat'] = DF['latitude']
        DF['reported_long'] = DF['longitude']
         
        # add the source to the DF
        DF['source'] = 'cdec'
        DF['state'] = 'CA'
        DF['timezone'] = 'PDT' # need to check with Andrew
         
        DF = DF.where((pd.notnull(DF)), None)
        
        # insert the dataframe into the database
        self.db.insert_data(DF, description='CDEC metadata', metadata=True)
        
        
        
#     def data(self):
#         """
#         Retrieve the data from Mesowest. 
#         """
#         
#         # deteremine the client/s for processing
#         client = self.config['client']
#         self._logger.info('Client for Mesowest data collection: {}'.format(client))
#         
#         # query to get the mesowest stations for the given client
#         qry = "SELECT primary_id FROM tbl_stations_view WHERE source='mesowest' AND client='{}'"
#         cursor = self.db.cnx.cursor()
#         
#         # get the current local time
#         mnt = pytz.timezone(self.config['timezone'])
#         if self.config['end_time'] is None:
#             endTime = pd.Timestamp('now')
#         else:
#             endTime = pd.to_datetime(self.config['end_time'])
#         endTime = mnt.localize(endTime)
#         endTime = endTime.tz_convert('UTC')
#         
#         # if a start time is specified localize it and convert to UTC
#         if self.config['start_time'] is not None:
#             startTime = pd.to_datetime(self.config['start_time'])
#             startTime = mnt.localize(startTime)
#             startTime = startTime.tz_convert('UTC')
#         
#         # go through each client and get the stations
#         for cl in client:
#             self._logger.info('Retrieving current data for client {}'.format(cl))
#             
#             cursor.execute(qry.format(cl))
#             stations = cursor.fetchall()
#             
#             # go through each and get the data
#             for stid in stations:
#                 stid = stid[0]
#                         
#                 if self.config['start_time'] is None:        
#                     # determine the last value for the station
#                     qry = "SELECT max(date_time) + INTERVAL 1 MINUTE AS d FROM tbl_level0 WHERE station_id='%s'" % stid
#                     cursor.execute(qry)
#                     startTime = cursor.fetchone()[0]                 
#                 
#                     if startTime is not None:
#                         startTime = pd.to_datetime(startTime, utc=True)
#                     else:             
#                         # start of the water year, do a local time then convert to UTC       
#                         wy = self.water_day(endTime)
#                         startTime = pd.to_datetime(datetime(wy-1, 10, 1), utc=False)
#                         startTime = mnt.localize(startTime)
#                         startTime = startTime.tz_convert('UTC')
#                    
#                 self._logger.debug('Retrieving data for station {} between {} and {}'.format(
#                     stid, startTime.strftime('%Y-%m-%d %H:%M'), endTime.strftime('%Y-%m-%d %H:%M'))) 
#                 data = self.currentMesowestData(startTime, endTime, stid)
# #                  
#                 if data is not None:
#                     df = self.meso2df(data)
#                     self.db.insert_data(df, description='Mesowest current data', data=True)
#         
#         
#         cursor.close()
#         
#         
#     def currentMesowestData(self, startTime, endTime, stid):
#         """
#         Call Mesowest for the data in bbox between startTime and endTime
#         """
#         
#         # set the parameters for the Mesowest query and build
#         p = self.params
#         p['start'] = startTime.strftime('%Y%m%d%H%M')      # start time
#         p['end'] = endTime.strftime('%Y%m%d%H%M')          # end time
#         p['stid'] = stid
#         
#         m = Meso(token=p['token'])
#         
#         try:
#             data = m.timeseries(start=p['start'], end=p['end'], obstimezone=p['obstimezone'],
#                                         stid=p['stid'], units=p['units'], vars=p['vars'])
#         except Exception as e:
#             self._logger.warn('{} -- {}'.format(stid, e))
#             data = None
#         
#         return data
#     
#     def meso2df(self, data):
#         """
#         Parse the Mesowest retuned data and parse the output into
#         a pandas dataframe
#         
#         Args:
#             data: dict returned from Mesowest
#         """
#         s = data['STATION'][0]
#         
#         # determine station id
#         station_id = str(s['STID'])
#         
#         # map the variables that where returned with what the names are
#         var = s['SENSOR_VARIABLES'].keys()
#         v = {}
#         for i in s['SENSOR_VARIABLES']:
#             if s['SENSOR_VARIABLES'][i]:
#                 v[list(s['SENSOR_VARIABLES'][i].keys())[0]] = i
#                      
#         # convert to dataframe
#         r = pd.DataFrame(s['OBSERVATIONS'], columns=s['OBSERVATIONS'].keys())  # preserve column order
#         
#         # convert to date_time from the returned format to MySQL format
#         r['date_time'] = pd.to_datetime(r['date_time']) 
#         r['date_time'] = r['date_time'].dt.strftime('%Y-%m-%d %H:%M')
#         
#         # rename the columns and make date time the index    
#         r.rename(columns = v, inplace=True)
# #         r = r.set_index('date_time')
#         vkeep = r.columns.isin(var)
#         r = r[r.columns[vkeep]]  # only take those that we wanted in case something made it through
#         
#         # add the station_id
#         r['station_id'] = station_id
#             
#         return r

  
    
