# TODO:
# - Auto detect song, album, playlist from url in wizard mode
# - Add logging to custom exceptions, and catch them!
# - Have a list of failed songs
# - Patch the front end into the backend
# - Add a progress bar
# - Add multi-threading
import argparse
import sys
from apis.spotify import Spotify
from apis.youtube import YouTube
import utils
import login
import re
from downloader import SpotifyDownloader

from const import colours, SpotifyAuthType, DEFAULT_MIN_VIEWS_FOR_DOWNLOAD, DEFAULT_MAX_LENGTH_FOR_DOWNLOAD, LIKED_KEYWORD, HELP_URL

def get_bitrate_from_quality(quality):
    if quality == "low":
        return 50000
    elif quality == "medium":
        return 80000
    elif quality == "high":
        return 256000
    else:
        return int(quality)

def validate_quality(quality):
    valid_strings = ['low', 'medium', 'high']
    if quality in valid_strings:
        return quality
    try:
        bitrate = int(quality)
        if 48000 <= bitrate <= 256000:  # Typical YouTube bitrate ranges
            return quality
        else:
            raise argparse.ArgumentTypeError(f"Bitrate outside of typical YouTube range (64 kbps to 320 kbps): {quality}")
    except ValueError:
        raise argparse.ArgumentTypeError(f"\nInvalid quality/bitrate: {quality}\n")

def validate_spotify_url(url):
    """Validate the Spotify URL and infer the type."""
    song_pattern = r"https://open\.spotify\.com/track/[A-Za-z0-9?=\-]+"
    playlist_pattern = r"https://open\.spotify\.com/playlist/[A-Za-z0-9?=\-]+"
    private_playlist_pattern = r"https://open\.spotify\.com/playlist/[A-Za-z0-9?=[A-Za-z0-9&pt=[A-Za-z0-9\-]+"
    album_pattern = r"https://open\.spotify\.com/album/[A-Za-z0-9?=\-]+"

    if url == LIKED_KEYWORD:
        return url
    elif re.match(song_pattern, url):
        return 'song'
    elif re.match(private_playlist_pattern, url):
        return 'private_playlist'
    elif re.match(playlist_pattern, url):
        return 'playlist'
    elif re.match(album_pattern, url):
        return 'album'
    else:
        print("")
        raise ValueError(f"Invalid Spotify URL: {url}\n")

def get_user_input():
    """Prompt the user for input when no arguments are supplied."""

    # Validate and infer the type of content from the URL
    while True:
        try:
            url = input(f"{colours.OKGREEN}Please provide a Spotify URL (right click, share, copy link) or '{LIKED_KEYWORD}':{colours.ENDC} \n\n> ")
            choice = validate_spotify_url(url)
            break
        except ValueError as e:
            print(f"{colours.FAIL}Error:{colours.ENDC}{e}")

    # Validate quality input
    quality = input(f"\n{colours.OKGREEN}Which quality would you like?{colours.ENDC} (Options: {colours.HEADER}low{colours.ENDC}, {colours.HEADER}medium{colours.ENDC}, {colours.HEADER}high{colours.ENDC}, or specify bitrate up to 320): ").strip()

    while quality not in ['low', 'medium', 'high'] and not quality.isdigit():
        quality = input(f"{colours.WARNING}Invalid quality.{colours.ENDC} Please choose between {colours.HEADER}low{colours.ENDC}, {colours.HEADER}medium{colours.ENDC}, {colours.HEADER}high{colours.ENDC}, or provide a specific bitrate: ").strip()

    # User authentication only
    authtype = SpotifyAuthType.USER

    return choice, url, quality, authtype

def main(playlist=None, song=None, album=None, private_playlist=False, liked=False, quality=None, min_views=None, max_length=None, disable_threading=False):
    # Always use user authentication
    authtype = SpotifyAuthType.USER

    # Validate the URL
    arg_name = 'song' if song else 'playlist' if playlist and not private_playlist else 'private_playlist' if playlist and private_playlist else 'album' if album else None
    url = song or playlist or album

    if not (url or liked):
        print(f"{colours.FAIL}Error: You must specify a song, playlist, album, or '{LIKED_KEYWORD}' to download.{colours.ENDC}")
        parser.print_help()
        sys.exit(1)
    
    url_type = validate_spotify_url(url) if url != None else LIKED_KEYWORD
    if url_type == 'private_playlist':
        private_playlist = True

    if (song and url_type != 'song') or (playlist and url_type not in ['playlist', 'private_playlist']) or (album and url_type != 'album'):
        print(f"{colours.FAIL}Error: {arg_name} argument provided but value is a {url_type}{colours.ENDC}")
        sys.exit(1)

    # Login if needed
    if not login.is_user_logged_in():
        login.do_user_login()

    print(f"\n{colours.CVIOLETBG2}Chosen Settings{colours.ENDC}\n")
    
    if playlist:
        if private_playlist:
            print(f"{colours.OKGREEN}Private Playlist{colours.ENDC}: {playlist}")
        else:
            print(f"{colours.OKGREEN}Playlist{colours.ENDC}: {playlist}")

    if song:
        print(f"{colours.OKGREEN}Song{colours.ENDC}: {song}")

    if album:
        print(f"{colours.OKGREEN}Album{colours.ENDC}: {album}")

    if liked:
        print(f"{colours.OKGREEN}Liked Songs{colours.ENDC}")
    
    if quality:
        bitrate = get_bitrate_from_quality(quality)
        print(f"{colours.OKGREEN}Song quality / bitrate{colours.ENDC}: {quality} / {bitrate} bps")

    if min_views != DEFAULT_MIN_VIEWS_FOR_DOWNLOAD:
        print(f"{colours.OKGREEN}Minimum view count{colours.ENDC}: {min_views}")

    if max_length != DEFAULT_MAX_LENGTH_FOR_DOWNLOAD:
        print(f"{colours.OKGREEN}Maximum video length{colours.ENDC}: {max_length}")
        
    print(f"{colours.OKGREEN}Accessing Spotify as logged in user {colours.ENDC}")
    
    if disable_threading:
        print(f"{colours.WARNING}Threading is disabled. Downloads may be slower.{colours.ENDC}")

    spotify = Spotify(authtype)
    youtube = YouTube()

    downloader = SpotifyDownloader(spotify, youtube, get_bitrate_from_quality(quality), max_length, min_views)

    success = False

    if(song):
        success = downloader.download_track(song)
    elif(playlist):
        success = downloader.download_playlist(playlist)
    elif(album):
        success = downloader.download_album(album)
    elif(liked):
        success = downloader.download_liked_songs()

    downloader.rm_tmp_folder()

    if(success):
        print(f"\n{colours.OKGREEN}Download complete!{colours.ENDC} (check downloads folder)\n")
    else:
        print(f"\n{colours.FAIL}Download failed!{colours.ENDC} If you need help, please visit {HELP_URL}\n\n")

if __name__ == "__main__":

    if len(sys.argv) > 1:

        parser = argparse.ArgumentParser(description="spotify2mp3: Download songs from Spotify by searching them on YouTube and converting the audio.")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("-p", "--playlist", "--list", help="Specify a playlist URL or ID to download. Private playlists must be placed in quotes '<playlist_url>' ", type=str)
        group.add_argument("-s", "--song", "--single", "-t", "--track", help="Specify a song URL or ID to download", type=str)
        group.add_argument("-a", "--album", help="Specify an album URL or ID to download", type=str)
        group.add_argument("-l", f"--{LIKED_KEYWORD}", help=f"Retrieves user's {LIKED_KEYWORD} songs", action="store_true")

        parser.add_argument("-q", "--quality", help="Specify the song download quality or bitrate", type=validate_quality, default="high")
        parser.add_argument("--min-views", help="Minimum view count on YouTube", type=int, default=DEFAULT_MIN_VIEWS_FOR_DOWNLOAD)
        parser.add_argument("--max-length", help="Maximum video length on YouTube in minutes", type=int, default=DEFAULT_MAX_LENGTH_FOR_DOWNLOAD)
        parser.add_argument("--disable-threading", help="Disables multiple threads to download songs.", action="store_true")
        # Remove login argument as it's now always required

        args = parser.parse_args()

        main(playlist=args.playlist, song=args.song, album=args.album, liked=args.liked, quality=args.quality, min_views=args.min_views, max_length=args.max_length, disable_threading=args.disable_threading)

    else:  # If no command-line arguments are provided, use wizard mode.
        utils.print_splash_screen()

        choice, url, quality, authtype = get_user_input()
        if choice == 'song':
            main(song=url, quality=quality, min_views=DEFAULT_MIN_VIEWS_FOR_DOWNLOAD, max_length=DEFAULT_MAX_LENGTH_FOR_DOWNLOAD)
        elif choice == 'playlist':
            main(playlist=url, quality=quality, min_views=DEFAULT_MIN_VIEWS_FOR_DOWNLOAD, max_length=DEFAULT_MAX_LENGTH_FOR_DOWNLOAD)
        elif choice == 'private_playlist':
            main(playlist=url, private_playlist=True, quality=quality, min_views=DEFAULT_MIN_VIEWS_FOR_DOWNLOAD, max_length=DEFAULT_MAX_LENGTH_FOR_DOWNLOAD)
        elif choice == 'album':
            main(album=url, quality=quality, min_views=DEFAULT_MIN_VIEWS_FOR_DOWNLOAD, max_length=DEFAULT_MAX_LENGTH_FOR_DOWNLOAD)
        elif choice == LIKED_KEYWORD:
            main(liked=True, quality=quality, min_views=DEFAULT_MIN_VIEWS_FOR_DOWNLOAD, max_length=DEFAULT_MAX_LENGTH_FOR_DOWNLOAD)
        else:
            print(f"{colours.FAIL}Invalid choice!{colours.ENDC}")
            sys.exit(1)