import sys
import os
import shutil
import time
import string
from pathlib import Path
import ssl
import re
import json

from const import colours
from pytubefix import YouTube as pytubeYouTube
from youtube_search import YoutubeSearch
from exceptions import SpotifyAlbumNotFound, SpotifyTrackNotFound, SpotifyPlaylistNotFound, ConfigVideoMaxLength, ConfigVideoLowViewCount, YoutubeItemNotFound
from apis.spotify import Spotify
from utils import resave_audio_clip_with_metadata

ssl._create_default_https_context = ssl._create_stdlib_context

class YouTube:
    def __init__(self):
        pass

    # Searches for a YouTube video
    def search(self, search_query, max_length, min_view_count, search_count=1):
        youtube_results = YoutubeSearch(search_query, max_results=search_count).to_json()

        if len(json.loads(youtube_results)['videos']) < 1:
            raise YoutubeItemNotFound('Skipped song -- Could not load from YouTube')

        youtube_videos = json.loads(youtube_results)['videos']
        videos_meta = []

        for video in youtube_videos:
            youtube_video_duration = video['duration'].split(':')
            youtube_video_duration_seconds = int(youtube_video_duration[0]) * 60 + int(youtube_video_duration[1])

            youtube_video_views = re.sub('[^0-9]', '', video['views'])
            youtube_video_viewcount_safe = int(youtube_video_views) if youtube_video_views.isdigit() else 0

            videos_meta.append((video, youtube_video_duration_seconds, youtube_video_viewcount_safe))

        sorted_videos = sorted(videos_meta, key=lambda vid: vid[2], reverse=True)
        chosen_video = sorted_videos[0]

        youtube_video_link = "https://www.youtube.com" + chosen_video[0]['url_suffix']

        if chosen_video[1] >= max_length:
            raise ConfigVideoMaxLength(f'Length {chosen_video[1]}s exceeds MAX_LENGTH value of {max_length}s [{youtube_video_link}]')

        if chosen_video[2] <= min_view_count:
            raise ConfigVideoLowViewCount(f'View count {chosen_video[2]} does not meet MIN_VIEW_COUNT value of {min_view_count} [{youtube_video_link}]')
    
        return youtube_video_link

    def download(self, url, audio_bitrate):
        youtube_video = pytubeYouTube(url, use_po_token=True)

        if youtube_video.age_restricted:
            youtube_video.bypass_age_gate()

        # Select best audio stream based on the provided bitrate
        audio_streams = youtube_video.streams.filter(only_audio=True).order_by('abr').desc()
        selected_stream = None

        for stream in audio_streams:
            abr_kbps = int(re.sub(r'\D', '', stream.abr))
            if abr_kbps <= audio_bitrate / 1000:
                selected_stream = stream
                break
        if not selected_stream:
            selected_stream = audio_streams.last()  # fallback to last (lowest bitrate if none match)

        # Download selected stream
        yt_tmp_out = selected_stream.download(output_path="./temp/")
        
        return yt_tmp_out, int(selected_stream.abr.rstrip('kbps')) * 1000


class SpotifyDownloader:
    def __init__(self, spotify: Spotify, youtube: YouTube, audio_quality=1000000, max_length=60*30, min_view_count=10000):
        self.spotify_client = spotify
        self.youtube_client = youtube
        self.audio_quality = audio_quality
        self.max_length = max_length
        self.min_view_count = min_view_count

    def download_album(self, playlist_url):
        skipped_songs = 0

        print(f"\n{colours.OKBLUE}[!] Retrieving Spotify album")

        try:
            album = self.spotify_client.album(playlist_url)

            self.prep_folder("downloads/albums/" + album.get_title(True))

            tracks = album.get_tracks()

            print(f"\n{colours.OKBLUE}[!] Found {len(tracks)} tracks in album.")
            
            time.sleep(3)

            output_path = "downloads/albums/" + album.get_title(True) + "/"
            self.download_tracks(output_path, tracks)

            return True
        
        except SpotifyAlbumNotFound as e:
            print(f"\n{colours.FAIL}Error: {colours.ENDC}{colours.WARNING}Album does not exist (e: {e}).{colours.ENDC}\n")
            sys.exit(1)

    def download_tracks(self, output_path, tracks):
        skipped_tracks = []

        idx_max = len(tracks)
        for i in range(idx_max):
            try:
                track = tracks[i]
                self.download_track(None, track, i, idx_max, output_path, True)

            except SpotifyTrackNotFound as e:
                print(f"   - {colours.WARNING}[!] Skipped a song we could not find.{colours.ENDC} {e}")
                skipped_tracks.append((track, e))
            
            except YoutubeItemNotFound as e:
                print(f"   - {colours.WARNING}[!] Skipped a song found on Spotify but not on YouTube.{colours.ENDC}\n")
                skipped_tracks.append((track, e))

            except ConfigVideoMaxLength as e:
                print(f"\n{colours.WARNING}[!] Skipped a song - Song length exceeds max length.{colours.ENDC}\n")
                skipped_tracks.append((track, e))
            
            except ConfigVideoLowViewCount as e:
                print(f"\n{colours.WARNING}[!] Skipped a song - View count below minimum threshold.\n")
                skipped_tracks.append((track, e))

        if len(skipped_tracks) > 0:
            print(f"\n{colours.WARNING}[!] Skipped {len(skipped_tracks)} songs.{colours.ENDC}\n")
            for (track, reason) in skipped_tracks:
                print(f"    {track.get_title(True)} {colours.WARNING}[{reason}]{colours.ENDC}")

        return skipped_tracks

    def download_track(self, track_url=None, track=None, idx=0, idx_max=0, output_path=None, as_sub_function=False):
        try:
            output_path = output_path if output_path else "downloads/tracks/"

            if track_url:
                track = self.spotify_client.track(track_url)
            else:
                if not track:
                    raise Exception("No Track was supplied to download track!")
                
            if track:
                print(f"\n{colours.OKGREEN}Searching for song [{idx+1}/{idx_max}]: {track.get_title(True)} by {track.get_artist()}")
            
            track_title = re.sub(r'[\\/:*?"<>|]', '_', track.get_title(True))  # Sanitize filename
            track_path = os.path.join(output_path, f"{track_title}.mp3")

            self.prep_folder(output_path)
            if self.file_exists(track_path):
                print(f"{colours.OKCYAN}   - File exists, skipping.")
                return True
                
            searchable_name = track.get_searchable_title()

            youtube_link = self.youtube_client.search(searchable_name, self.max_length, self.min_view_count)

            print(f"{colours.ENDC}   - Downloading, please wait{colours.ENDC}")

            video_downloaded_path, self.audio_quality = self.youtube_client.download(youtube_link, self.audio_quality)

            print(f"{colours.ENDC}   - Converting and adding metadata{colours.ENDC}")

            resave_audio_clip_with_metadata(video_downloaded_path, track.get_metadata(), track_path, self.audio_quality)

            print(f"{colours.ENDC}   - Done!")

            return True

        except SpotifyTrackNotFound as e:
            if not as_sub_function:
                print(f"\n{colours.FAIL}Error: {colours.ENDC}Could not find song online (e: {e}).{colours.ENDC}\n")
                return False
            else:
                raise e

    def prep_folder(self, folder_name):
        Path(folder_name).mkdir(parents=True, exist_ok=True)
        Path('temp/').mkdir(parents=True, exist_ok=True)

    def file_exists(self, file_path):
        return Path.exists(Path(file_path))

    def rm_tmp_folder(self):
        shutil.rmtree('./temp')


if __name__ == "__main__":
    pass