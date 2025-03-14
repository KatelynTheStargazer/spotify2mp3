from exceptions import InvalidSpotifyURL, SpotifyAlbumNotFound, SpotifyTrackNotFound, SpotifyPlaylistNotFound, SpotifyRetrievalError
import re
import os
import sys

import login

import tekore as tk

import const

# Add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Spotify:

    def __init__(self, authType: const.SpotifyAuthType):
        if authType == const.SpotifyAuthType.USER:
            token = login.get_user_token()
        else:
            raise ValueError('Only user authentication is supported. Please use SpotifyAuthType.USER.')

        if token is None:
            raise ValueError('Error retrieving access token for user refresh token.')

        self.tekore_spotify = tk.Spotify(token)

    def likedSongs(self):
        return SpotifyLikedSongs(self)

    def playlist(self, playlist_url):
        if not re.match(r"https://open\.spotify\.com/playlist/[A-Za-z0-9?=\-]+", playlist_url):
            raise InvalidSpotifyURL(
                f"Invalid Spotify Playlist URL: {playlist_url}")
        return SpotifyPlaylist(self, playlist_url)

    def track(self, track_url):
        if not re.match(r"https://open\.spotify\.com/track/[A-Za-z0-9?=\-]+", track_url):
            raise InvalidSpotifyURL(f"Invalid Spotify Track URL: {track_url}")
        return SpotifyTrack(self, track_url)

    def album(self, album_url):
        if not re.match(r"https://open\.spotify\.com/album/[A-Za-z0-9?=\-]+", album_url):
            raise InvalidSpotifyURL(f"Invalid Spotify Album URL: {album_url}")
        return SpotifyAlbum(self, album_url)

class SpotifyPlaylist():
    def __init__(self, base: Spotify, resource_url):
        self.base = base
        self.resource_url = resource_url
        self.resource_id_match = re.search(
            r"/playlist/([a-zA-Z0-9]+)", self.resource_url)
        self.resource_id = self.resource_id_match.group(1)
        self.playlist_metadata = {}

    def load(self):

        try:
            playlist = self.base.tekore_spotify.playlist(self.resource_id)
            
            # handles spotify API paging internally
            playlist_tracks = self.base.tekore_spotify.all_items(playlist.tracks)
            tracks = []

            for model in playlist_tracks:
                external_urls = model.track.external_urls

                this_track = SpotifyTrack(self.base, external_urls.get("spotify", ""))
                this_track.load(model.track)
                tracks.append(this_track)

            if playlist:
                self.playlist_metadata = {
                    "title": playlist.name,
                    "image_url": playlist.images[0].url if len(playlist.images) > 0 else const.UNKNOWN_ALBUM_COVER_URL,
                    "tracks": tracks,
                }
            else:
                raise SpotifyPlaylistNotFound(
                    "Failed to fetch playlist data from Spotify API.")

        except tk.HTTPError as e:
            if e.response.status_code == 404:
                raise SpotifyPlaylistNotFound("Playlist not found.")
            
            raise SpotifyRetrievalError(f'Error retrieving playlist:{e}')

    def get_title(self, sanitize=False):

        if not self.playlist_metadata:
            self.load()

        playlist_title = self.playlist_metadata.get(
            "title", "Unknown Playlist Name")

        if not sanitize:
            return playlist_title
        else:
            return "".join(
                [
                    current_character
                    for current_character in playlist_title
                    if current_character in const.LEGAL_PATH_CHARACTERS
                ]
            )

    def get_cover_art_url(self):

        if not self.playlist_metadata:
            self.load()

        cover_art_url = self.playlist_metadata.get(
            "image_url", const.UNKNOWN_ALBUM_COVER_URL)

        return cover_art_url

    def get_tracks(self):

        if not self.playlist_metadata:
            self.load()

        return self.playlist_metadata.get("tracks", [])

    def get_metadata(self):

        if not self.playlist_metadata:
            self.load()

        return self.playlist_metadata


class SpotifyAlbum():
    def __init__(self, base: Spotify, resource_url):
        self.base = base
        self.resource_url = resource_url
        self.resource_id_match = re.search(
            r"/album/([a-zA-Z0-9]+)", self.resource_url)
        self.resource_id = self.resource_id_match.group(1)
        self.album_metadata = {}

    def load(self):

        try:
            album = self.base.tekore_spotify.album(self.resource_id)
            # handles spotify API paging internally
            album_tracks = self.base.tekore_spotify.all_items(album.tracks)
            tracks = []

            for model in album_tracks:
                external_urls = model.external_urls

                this_track = SpotifyTrack(self.base, external_urls.get("spotify", ""))
                this_track.load()
                tracks.append(this_track)

            if album:
                self.album_metadata = {
                    "title": album.name,
                    "image_url": album.images[0].url if len(album.images) > 0 else const.UNKNOWN_ALBUM_COVER_URL,
                    "tracks": tracks,
                }
            else:
                raise SpotifyAlbumNotFound(
                    "Failed to fetch album data from Spotify API.")

        except tk.HTTPError as e:
            raise SpotifyRetrievalError(f'Error retrieving album:{e}')

    def get_title(self, sanitize=False):

        if not self.album_metadata:
            self.load()

        album_title = self.album_metadata.get("title", "Unknown Album Name")

        if not sanitize:
            return album_title
        else:
            return "".join(
                [
                    current_character
                    for current_character in album_title
                    if current_character in const.LEGAL_PATH_CHARACTERS
                ]
            )

    def get_cover_art_url(self):

        if not self.album_metadata:
            self.load()

        return self.album_metadata.get("image_url", const.UNKNOWN_ALBUM_COVER_URL)

    def get_tracks(self):

        if not self.album_metadata:
            self.load()

        return self.album_metadata.get("tracks", [])

    def get_metadata(self):

        if not self.album_metadata:
            self.load()

        return self.album_metadata


class SpotifyTrack():
    def __init__(self, base: Spotify, resource_url):
        self.base = base
        self.resource_url = resource_url
        self.resource_id_match = re.search(
            r"/track/([a-zA-Z0-9]+)", self.resource_url)
        self.resource_id = self.resource_id_match.group(1)
        self.track_metadata = {}

    def load(self, track_data=None):

        if track_data == None:

            try:
                track_data = self.base.tekore_spotify.track(self.resource_id)
            except tk.HTTPError as e:
                raise SpotifyRetrievalError(f'Error retrieving track:{e}')

        if track_data:

            album_data = track_data.album
            artists_data = track_data.artists
            external_urls = track_data.external_urls
            album_images = album_data.images

            self.track_metadata = {
                "title": track_data.name,
                "artist": [artist.name for artist in artists_data],
                "album": album_data.name,
                "release_date": album_data.release_date,
                "track_num": track_data.track_number,
                "disc_num": track_data.disc_number,
                "isrc": track_data.external_ids.get("isrc", False),
                "comments": {
                    "Spotify Track URL": external_urls.get("spotify", ""),
                    "Spotify Album URL": album_data.external_urls.get("spotify", ""),
                    "Spotify Artist URL": artists_data[0].external_urls.get("spotify", ""),
                    "Duration (ms)": str(track_data.duration_ms),
                    "Album Type": album_data.album_type,
                },
                "image_url": album_images[0].url if len(album_images) > 0 else const.UNKNOWN_ALBUM_COVER_URL,
            }

        else:
            raise SpotifyTrackNotFound(
                "Failed to fetch track data from Spotify API.")

    def get_title(self, sanitize=False):

        if not self.track_metadata:
            self.load()

        track_title = self.track_metadata.get("title", "Unknown Title")

        if not sanitize:
            return track_title
        else:
            return "".join(
                [
                    current_character
                    for current_character in track_title
                    if current_character in const.LEGAL_PATH_CHARACTERS
                ]
            )

    def get_artist(self, sanitize=False):

        if not self.track_metadata:
            self.load()

        artist_name = " ".join(
            self.track_metadata.get("artist", "Unknown artist"))

        if not sanitize:
            return artist_name

        else:
            return "".join(
                [
                    current_character
                    for current_character in artist_name
                    if current_character in const.LEGAL_PATH_CHARACTERS
                ]
            )

    def get_searchable_title(self):

        if not self.track_metadata:
            self.load()

        searchable_title = (
            self.track_metadata.get("title", "Unknown Title")
            + " - "
            + " ".join(self.track_metadata.get("artist"))
        )

        return searchable_title

    def get_cover_art_url(self):

        if not self.track_metadata:
            self.load()

        cover_art_url = self.track_metadata.get(
            "image_url", const.UNKNOWN_ALBUM_COVER_URL)

        return cover_art_url

    def get_metadata(self):

        if not self.track_metadata:
            self.load()

        return self.track_metadata


class SpotifyLikedSongs():
    def __init__(self, base: Spotify):
        self.base = base
        self.playlist_metadata = {}

    def load(self):

        try:
            playlist = self.base.tekore_spotify.saved_tracks(limit=50)
            # handles spotify API paging internally
            playlist_tracks = self.base.tekore_spotify.all_items(playlist)
            tracks = []

            for model in playlist_tracks:
                external_urls = model.track.external_urls

                this_track = SpotifyTrack(self.base, external_urls.get("spotify", ""))
                this_track.load(model.track)
                tracks.append(this_track)

            if playlist:
                images = self.base.tekore_spotify.current_user().images
                self.playlist_metadata = {
                    "title": "Liked Songs",
                    "image_url": images[0].url if len(images) > 0 else const.UNKNOWN_ALBUM_COVER_URL,
                    "tracks": tracks,
                }
            else:
                raise SpotifyPlaylistNotFound(
                    "Failed to fetch playlist data from Spotify API.")

        except tk.HTTPError:
            raise SpotifyRetrievalError("Error in retrieving playlist!")
        
    def get_title(self, sanitize=False):

        if not self.playlist_metadata:
            self.load()

        playlist_title = self.playlist_metadata.get(
            "title", "Unknown Playlist Name")

        if not sanitize:
            return playlist_title
        else:
            return "".join(
                [
                    current_character
                    for current_character in playlist_title
                    if current_character in const.LEGAL_PATH_CHARACTERS
                ]
            )

    def get_tracks(self):

        if not self.playlist_metadata:
            self.load()

        return self.playlist_metadata.get("tracks", [])


if __name__ == "__main__":
    pass