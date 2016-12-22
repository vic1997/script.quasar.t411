# coding: utf-8

import unicodedata
import re
import json
import xbmc
import xbmcaddon
import urllib
from quasar import provider
import base64
import hashlib
import bencode
from threading import Thread
import Queue



# Addon Script information
__addonID__ = provider.ADDON.getAddonInfo('id')
API_URL = provider.ADDON.getSetting("base_url")
username = provider.ADDON.getSetting("username")
password = provider.ADDON.getSetting("password")
titreVF = provider.ADDON.getSetting("titreVF")
passkey = provider.ADDON.getSetting("passkey")
icon = xbmcaddon.Addon().getAddonInfo('icon')
filtre_film = provider.ADDON.getSetting("filtre_f")
filtre_serie = provider.ADDON.getSetting("filtre_s")
serie_en_plus = provider.ADDON.getSetting("serie_en_plus")


limit = 15 #provider.ADDON.getSetting("limit")

USER_CREDENTIALS_FILE = xbmc.translatePath("special://profile/addon_data/%s/token.txt" % __addonID__)

user_credentials = {}

tmdbUrl = 'http://api.themoviedb.org/3'
tmdbKey = '8d0e4dca86c779f4157fc2c469c372ca'    # mancuniancol's API Key.

# Categories ID /categories/tree
CAT_VIDEO = '210'
CAT_MOVIE = '631'
CAT_TV = '433'
CAT_MOVIE_ANIM = '455'
CAT_TV_ANIME = '637'

new_url = 'https://api.t411.li'
if API_URL == 'https://api.t411.ch':
    provider.ADDON.setSetting("base_url", new_url)
    API_URL = new_url

def _init() :
    global user_credentials
    provider.log.info("Get user credentials and authentificate it, if any credentials defined use token stored in user file")
    try :
        with open(USER_CREDENTIALS_FILE) as user_cred_file:
            user_credentials = json.loads(user_cred_file.read())
            provider.log.info("Get local credentials")
            provider.log.debug(user_credentials)
        if 'uid' not in user_credentials or 'token' not in user_credentials:
            raise Exception('Wrong data found in user file')
        # Get user details & check if token still valid
        #response = call('/users/profile/' + user_credentials['uid'])
        #provider.log.debug(response)
        #else:
        # we have to ask the user for its credentials and get the token from
        # the API
        #self._auth(user, password)
    except IOError as e:
        # Try to auth user from credentials in parameters
        _auth(username, password)
    #except Exception as e:
    #    raise Exception('Error while reading user credentials: %s.' %
    #    e.message)
def _auth(username, password) :
    global user_credentials
    provider.log.info("Authentificate user and store token")
    user_credentials = call('/auth', {'username': username, 'password': password})
    print(user_credentials)
    if 'error' in user_credentials:
        raise Exception('Error while fetching authentication token: %s' % user_credentials['error'])
    # Create or update user file
    provider.log.info('file %s' % USER_CREDENTIALS_FILE)
    user_data = json.dumps({'uid': '%s' % user_credentials['uid'], 'token': '%s' % user_credentials['token']})
    with open(USER_CREDENTIALS_FILE, 'w') as user_cred_file:
        user_cred_file.write(user_data)
    return True
    

def call(method='', params=None) :
    provider.log.info("Call T411 API: %s%s" % (API_URL, method))
    if method != '/auth' :
        token = user_credentials['token']
        provider.log.info('token %s' % token)
        req = provider.POST('%s%s' % (API_URL, method), headers={'Authorization': token})
    else:
        req = provider.POST('%s%s' % (API_URL, method), data=provider.urlencode(params))
    if req.getcode() == 200:
        return req.json()
    else :
        raise Exception('Error while sending %s request: HTTP %s' % (method, req.getcode()))

# Default Search
def search(query, cat_id=CAT_MOVIE, terms=None, episode = False, season = False):
    provider.notify(message=str(query).replace('+',' ').title(), header="Quasar AlexP's [COLOR FF18F6F3]t411[/COLOR] Provider" , time=3000, image=icon)
    result = []
    threads = []
    q = Queue.Queue()
    provider.log.debug("QUERY : %s" % query)
    query = query.replace('+','%20')
    response = call('/torrents/search/%s&?limit=15&cid=%s%s' % (query, cat_id, terms))
    if episode or season: # search for animation series too
        response_tv_anim = response = call('/torrents/search/%s&?limit=15&cid=%s%s' % (query, CAT_TV_ANIME, terms))
        response['torrents'] = response['torrents'] + response_tv_anim['torrents']
    if episode and serie_en_plus == 'true':
        terms2 = terms[:-3] + '936'
        response2 = call('/torrents/search/%s&?limit=15&cid=%s%s' % (query, cat_id, terms2))
        response3 = call('/torrents/search/%s&?limit=15&cid=%s%s' % (query, CAT_TV_ANIME, terms2))
        response['torrents'] = response['torrents'] + response2['torrents'] + response3['torrents']
    provider.log.debug("Search results : %s" % response)
    # quasar send GET requests & t411 api needs POST
    # Must use the bencode tool :(
    
    for t in response['torrents'] :

        # Call each individual page in parallel
        thread = Thread(target=torrent2magnet, args = (t, q, user_credentials['token']))
        thread.start()
        threads.append(thread)

    # And get all the results
    for t in threads :
        t.join()
    while not q.empty():
        item = q.get()
        result.append({
                       "size":sizeof_fmt(item["size"]),
                       "seeds": item["seeds"], 
                       "peers": item["peers"], 
                       "name": item["name"],
                       "trackers": item["trackers"],
                       "info_hash": item["info_hash"],
                       "is_private": True,
                       "provider":"[COLOR FF18F6F3]t411[/COLOR]",
                       "icon": icon })
    return result

    
def search_episode(episode):
    pref_terms = ''
    if filtre_serie == 'true':
    
        termList = [[]] * 18
        # 7 : Video - Qualite
        termList[7] = [8,10,11,12,15,16,17,18,19,1162,1174,1175,1182,1208,1218,1233]
        # 9 : Video - Type
        termList[9] = [22,23,24,1045]
        # 17 : Video - Langue
        termList[17] = [1209,1210,1211,1212,1213,1214,1215,1216]
    
        # Get all settings correspondance
        for idx, term in enumerate(termList):
            for iTerm in term:
                if provider.ADDON.getSetting('%s_s' % iTerm) == 'true':
                    pref_terms += '&term[%s][]=%s' % (idx, iTerm)
               
    provider.log.debug("Search episode : name %(title)s, season %(season)02d, episode %(episode)02d" % episode)
    if(titreVF == 'true') :
        # Get the FRENCH title from TMDB
        provider.log.debug('Get FRENCH title from TMDB for %s' % episode['imdb_id'])
        response = provider.GET("%s/find/%s?api_key=%s&language=fr&external_source=imdb_id" % (tmdbUrl, episode['imdb_id'], tmdbKey))
        provider.log.debug(response)
        if response != (None, None):
            episode['title'] = response.json()['tv_results'][0]['name'].encode('utf-8').replace(' ','+')
            provider.log.info('FRENCH title :  %s' % episode['title'])
        else :
            provider.log.error('Error when calling TMDB. Use Quasar movie data.')
    
    # Get settings for TVShows, welcome to t411 API
    terms = pref_terms

    if(episode['season']):
        if episode['season'] < 25  or 27 < episode['season'] < 31 :
            real_s = int(episode['season']) + 967
            
        if episode['season'] == 25 :
            real_s = 994
            
        if 25 < episode['season'] < 28 :
            real_s = int(episode['season']) + 966
            
        terms += '&term[45][]=%s' % real_s

    if(episode['episode']):
        if episode['episode'] < 9 :
            real_ep = int(episode['episode']) + 936
        if 8 < episode['episode'] < 31 :
            real_ep = int(episode['episode']) + 937
        if 30 < episode['episode'] < 61 :
            real_ep = int(episode['episode']) + 1057
        
            
        terms += '&term[46][]=%s' % real_ep

    return search(episode['title'], CAT_TV, terms, episode = True)
    
def search_season(serie):
    pref_terms = ''
    if filtre_serie == 'true':
    
        termList = [[]] * 18
        # 7 : Video - Qualite
        termList[7] = [8,10,11,12,15,16,17,18,19,1162,1174,1175,1182,1208,1218,1233]
        # 9 : Video - Type
        termList[9] = [22,23,24,1045]
        # 17 : Video - Langue
        termList[17] = [1209,1210,1211,1212,1213,1214,1215,1216]
    
        # Get all settings correspondance
        for idx, term in enumerate(termList):
            for iTerm in term:
                if provider.ADDON.getSetting('%s_s' % iTerm) == 'true':
                    pref_terms += '&term[%s][]=%s' % (idx, iTerm)
                    
    terms = pref_terms
    terms += '&term[46][]=936'  # saison complete
    
    if(titreVF == 'true') :
        # Get the FRENCH title from TMDB
        provider.log.debug('Get FRENCH title from TMDB for %s' % serie['imdb_id'])
        response = provider.GET("%s/find/%s?api_key=%s&language=fr&external_source=imdb_id" % (tmdbUrl, serie['imdb_id'], tmdbKey))
        provider.log.debug(response)
        if response != (None, None):
            serie['title'] = response.json()['tv_results'][0]['name'].encode('utf-8').replace(' ','+')
            provider.log.info('FRENCH title :  %s' % serie['title'])
        else :
            provider.log.error('Error when calling TMDB. Use Quasar movie data.')
    
    if serie['season'] < 25  or 27 < serie['season'] < 31 :
        real_s = int(serie['season']) + 967
        
    if serie['season'] == 25 :
        real_s = 994
        
    if 25 < serie['season'] < 28 :
        real_s = int(serie['season']) + 966
    
    terms += '&term[45][]=%s' % real_s
    
    return search(serie['title'], CAT_TV, terms, season = True)
    

def search_movie(movie):
    pref_terms = ''
    if filtre_film == 'true':
         
        termList = [[]] * 18
        # 7 : Video - Qualite
        # termList[7] = [8,9,10,11,12,13,14,15,16,17,18,19,1162,1171,1174,1175,1182]
        termList[7] = [8,10,11,12,15,16,17,18,19,1162,1174,1175,1182,1208,1218,1233]
    
        # 9 : Video - Type
        termList[9] = [22,23,24,1045]
        # 17 : Video - Langue
        termList[17] = [540,541,542,719,720,721,1160]
    
        # Get all settings correspondance
        for idx, term in enumerate(termList):
            for iTerm in term:
                if provider.ADDON.getSetting('%s_f' % iTerm) == 'true':
                    pref_terms += '&term[%s][]=%s' % (idx, iTerm)
               
    if(titreVF == 'true') :
        #quasar 0.2 doesn't work well with foreing title. Get the FRENCH title from TMDB
        provider.log.debug('Get FRENCH title from TMDB for %s' % movie['imdb_id'])
        response = provider.GET("%s/movie/%s?api_key=%s&language=fr&external_source=imdb_id&append_to_response=alternative_titles" % (tmdbUrl, movie['imdb_id'], tmdbKey))
        if response != (None, None):
            response = response.json()
            movie['title'] = response['title'].encode('utf-8')
            if movie['title'].find(' : ') != -1:
                movie['title'] = movie['title'].split(' : ')[0] ## SPLIT LONG TITLE
                movie['title'] = movie['title'] + ' ' + response['release_date'].split('-')[0] ## ADD YEAR
            provider.log.info('FRENCH title :  %s' % movie['title'])
            global msg
            msg = movie['title']
        else :
            provider.log.error('Error when calling TMDB. Use quasar movie data.')
    return search(movie['title'], CAT_VIDEO, pref_terms)


def torrent2magnet(t, q, token):
    torrentdl = '/torrents/download/%s' % t["id"]
    response = provider.POST('%s%s' % (API_URL, torrentdl), headers={'Authorization': token})
    torrent = response.data
    if passkey is not '':
        key = re.compile('download([^"]+)announce').findall(torrent)
        key = key[0].split('/')[1]
        torrent=torrent.replace(key,passkey)
    metadata = bencode.bdecode(torrent)
    hashcontents = bencode.bencode(metadata['info'])
    digest = hashlib.sha1(hashcontents).hexdigest()
    trackers = [metadata["announce"]]
    
    # xbmc.log('Put Magnet in queue : name %s, size %s, seeds %s, peers %s' % (t["name"], t["size"], t["seeders"], t["leechers"]), xbmc.LOGDEBUG)
    q.put({"size": int(t["size"]), "seeds": int(t["seeders"]), "peers": int(t["leechers"]), "name": t["name"].encode('utf-8'), "trackers": trackers, "info_hash": digest })

def sizeof_fmt(num, suffix=''):
    for unit in ['','Ko','Mo','GB','To','Po','Eo','Zo']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


# Initialize account
_init()
#_auth()

# Registers the module in quasar
provider.register(search, search_movie, search_episode,search_season)
