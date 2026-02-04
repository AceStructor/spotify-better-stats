--
-- PostgreSQL database dump
--

\restrict sOfgedFv6wEyNRLLqhgxcRozFWribELaNyYcwdG7PVBphoRlhOcXzBizsnSiemo

-- Dumped from database version 16.11 (Debian 16.11-1.pgdg13+1)
-- Dumped by pg_dump version 16.11 (Ubuntu 16.11-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

ALTER TABLE IF EXISTS ONLY public.tracks DROP CONSTRAINT IF EXISTS workflow_id_fk;
ALTER TABLE IF EXISTS ONLY public.track_plays DROP CONSTRAINT IF EXISTS workflow_id_fk;
ALTER TABLE IF EXISTS ONLY public.artists DROP CONSTRAINT IF EXISTS workflow_id_fk;
ALTER TABLE IF EXISTS ONLY public.tracks DROP CONSTRAINT IF EXISTS tracks_artist_id_fkey;
ALTER TABLE IF EXISTS ONLY public.tracks DROP CONSTRAINT IF EXISTS tracks_album_id_fkey;
ALTER TABLE IF EXISTS ONLY public.track_plays DROP CONSTRAINT IF EXISTS track_plays_track_id_fkey;
ALTER TABLE IF EXISTS ONLY public.artist_genres DROP CONSTRAINT IF EXISTS artist_genres_genre_id_fkey;
ALTER TABLE IF EXISTS ONLY public.artist_genres DROP CONSTRAINT IF EXISTS artist_genres_artist_id_fkey;
ALTER TABLE IF EXISTS ONLY public.albums DROP CONSTRAINT IF EXISTS albums_artist_id_fkey;
DROP TRIGGER IF EXISTS trg_notify_workflow_progress ON public.workflow_state;
DROP TRIGGER IF EXISTS tracks_insert_trigger ON public.tracks;
DROP TRIGGER IF EXISTS track_plays_insert_trigger ON public.track_plays;
DROP TRIGGER IF EXISTS spotify_tracks_insert_trigger ON public.spotify_tracks;
DROP TRIGGER IF EXISTS artists_insert_trigger ON public.artists;
DROP INDEX IF EXISTS public.ux_tracks_identity;
ALTER TABLE IF EXISTS ONLY public.workflow_state DROP CONSTRAINT IF EXISTS workflow_state_pkey;
ALTER TABLE IF EXISTS ONLY public.tracks DROP CONSTRAINT IF EXISTS tracks_track_id_key;
ALTER TABLE IF EXISTS ONLY public.tracks DROP CONSTRAINT IF EXISTS tracks_pkey;
ALTER TABLE IF EXISTS ONLY public.tracks DROP CONSTRAINT IF EXISTS tracks_album_id_title_key;
ALTER TABLE IF EXISTS ONLY public.track_plays DROP CONSTRAINT IF EXISTS track_plays_track_id_played_at_key;
ALTER TABLE IF EXISTS ONLY public.track_plays DROP CONSTRAINT IF EXISTS track_plays_pkey;
ALTER TABLE IF EXISTS ONLY public.spotify_tracks DROP CONSTRAINT IF EXISTS spotify_tracks_track_id_played_at_key;
ALTER TABLE IF EXISTS ONLY public.spotify_tracks DROP CONSTRAINT IF EXISTS spotify_tracks_pkey;
ALTER TABLE IF EXISTS ONLY public.genres DROP CONSTRAINT IF EXISTS genres_pkey;
ALTER TABLE IF EXISTS ONLY public.genres DROP CONSTRAINT IF EXISTS genres_name_key;
ALTER TABLE IF EXISTS ONLY public.artists DROP CONSTRAINT IF EXISTS artists_pkey;
ALTER TABLE IF EXISTS ONLY public.artists DROP CONSTRAINT IF EXISTS artists_name_key;
ALTER TABLE IF EXISTS ONLY public.artist_genres DROP CONSTRAINT IF EXISTS artist_genres_pkey;
ALTER TABLE IF EXISTS ONLY public.albums DROP CONSTRAINT IF EXISTS albums_pkey;
ALTER TABLE IF EXISTS ONLY public.albums DROP CONSTRAINT IF EXISTS albums_artist_id_title_key;
ALTER TABLE IF EXISTS public.tracks ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.track_plays ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.spotify_tracks ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.genres ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.artists ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.albums ALTER COLUMN id DROP DEFAULT;
DROP TABLE IF EXISTS public.workflow_state;
DROP SEQUENCE IF EXISTS public.tracks_id_seq;
DROP TABLE IF EXISTS public.tracks;
DROP SEQUENCE IF EXISTS public.track_plays_id_seq;
DROP TABLE IF EXISTS public.track_plays;
DROP SEQUENCE IF EXISTS public.spotify_tracks_id_seq;
DROP TABLE IF EXISTS public.spotify_tracks;
DROP SEQUENCE IF EXISTS public.genres_id_seq;
DROP TABLE IF EXISTS public.genres;
DROP SEQUENCE IF EXISTS public.artists_id_seq;
DROP TABLE IF EXISTS public.artists;
DROP TABLE IF EXISTS public.artist_genres;
DROP SEQUENCE IF EXISTS public.albums_id_seq;
DROP TABLE IF EXISTS public.albums;
DROP FUNCTION IF EXISTS public.on_tracks_insert();
DROP FUNCTION IF EXISTS public.on_artists_insert();
DROP FUNCTION IF EXISTS public.notify_workflow_progress();
DROP FUNCTION IF EXISTS public.notify_track_play_insert();
DROP FUNCTION IF EXISTS public.notify_track_insert();
DROP FUNCTION IF EXISTS public.notify_spotify_track_insert();
DROP EXTENSION IF EXISTS pgcrypto;
--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: notify_track_play_insert(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.notify_track_play_insert() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    PERFORM pg_notify(
        'track_plays_inserted',
        row_to_json(NEW)::text
    );
    RETURN NEW;
END;
$$;


--
-- Name: notify_workflow_progress(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.notify_workflow_progress() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    PERFORM pg_notify(
		'workflow_progress',
		row_to_json(NEW)::text
	);

    RETURN NEW;
END;
$$;


--
-- Name: on_artists_insert(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.on_artists_insert() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE workflow_state
    SET genre_required = true
    WHERE workflow_id = NEW.workflow_id;

	PERFORM pg_notify(
        'artists_inserted',
        row_to_json(NEW)::text
    );

    RETURN NEW;
END;
$$;


--
-- Name: on_tracks_insert(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.on_tracks_insert() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE workflow_state
    SET yt_required = true
    WHERE workflow_id = NEW.workflow_id;

	PERFORM pg_notify(
        'tracks_inserted',
        row_to_json(NEW)::text
    );

    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: albums; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.albums (
    id integer NOT NULL,
    artist_id integer NOT NULL,
    title text NOT NULL,
    release_date date,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: albums_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.albums_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: albums_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.albums_id_seq OWNED BY public.albums.id;


--
-- Name: artist_genres; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.artist_genres (
    artist_id integer NOT NULL,
    genre_id integer NOT NULL
);


--
-- Name: artists; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.artists (
    id integer NOT NULL,
    name text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    workflow_id uuid
);


--
-- Name: artists_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.artists_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: artists_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.artists_id_seq OWNED BY public.artists.id;


--
-- Name: genres; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.genres (
    id integer NOT NULL,
    name text NOT NULL
);


--
-- Name: genres_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.genres_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: genres_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.genres_id_seq OWNED BY public.genres.id;


--
-- Name: track_plays; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.track_plays (
    id integer NOT NULL,
    track_id integer NOT NULL,
    played_at timestamp with time zone NOT NULL,
    skipped boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    workflow_id uuid
);


--
-- Name: track_plays_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.track_plays_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: track_plays_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.track_plays_id_seq OWNED BY public.track_plays.id;


--
-- Name: tracks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tracks (
    id integer NOT NULL,
    track_id text,
    artist_id integer NOT NULL,
    album_id integer NOT NULL,
    title text NOT NULL,
    duration_ms integer NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    youtube_code text,
    download_status text CHECK (download_status IN ('none', 'queued', 'downloading', 'done', 'error')) DEFAULT 'none' NOT NULL,
    file_path text,
    audio_format text,
    downloaded_at timestamp with time zone,
    download_error text,
    workflow_id uuid
);


--
-- Name: tracks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tracks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tracks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tracks_id_seq OWNED BY public.tracks.id;


--
-- Name: workflow_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_state (
    workflow_id uuid DEFAULT gen_random_uuid() NOT NULL,
    genre_required boolean DEFAULT false NOT NULL,
    yt_required boolean DEFAULT false NOT NULL,
    genre_done boolean DEFAULT false NOT NULL,
    yt_done boolean DEFAULT false NOT NULL,
    init_done boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: albums id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.albums ALTER COLUMN id SET DEFAULT nextval('public.albums_id_seq'::regclass);


--
-- Name: artists id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artists ALTER COLUMN id SET DEFAULT nextval('public.artists_id_seq'::regclass);


--
-- Name: genres id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.genres ALTER COLUMN id SET DEFAULT nextval('public.genres_id_seq'::regclass);


--
-- Name: track_plays id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.track_plays ALTER COLUMN id SET DEFAULT nextval('public.track_plays_id_seq'::regclass);


--
-- Name: tracks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tracks ALTER COLUMN id SET DEFAULT nextval('public.tracks_id_seq'::regclass);


--
-- Name: albums albums_artist_id_title_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.albums
    ADD CONSTRAINT albums_artist_id_title_key UNIQUE (artist_id, title);


--
-- Name: albums albums_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.albums
    ADD CONSTRAINT albums_pkey PRIMARY KEY (id);


--
-- Name: artist_genres artist_genres_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artist_genres
    ADD CONSTRAINT artist_genres_pkey PRIMARY KEY (artist_id, genre_id);


--
-- Name: artists artists_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artists
    ADD CONSTRAINT artists_name_key UNIQUE (name);


--
-- Name: artists artists_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artists
    ADD CONSTRAINT artists_pkey PRIMARY KEY (id);


--
-- Name: genres genres_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.genres
    ADD CONSTRAINT genres_name_key UNIQUE (name);


--
-- Name: genres genres_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.genres
    ADD CONSTRAINT genres_pkey PRIMARY KEY (id);


--
-- Name: track_plays track_plays_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.track_plays
    ADD CONSTRAINT track_plays_pkey PRIMARY KEY (id);


--
-- Name: track_plays track_plays_track_id_played_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.track_plays
    ADD CONSTRAINT track_plays_track_id_played_at_key UNIQUE (track_id, played_at);


--
-- Name: tracks tracks_album_id_title_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tracks
    ADD CONSTRAINT tracks_album_id_title_key UNIQUE (album_id, title);


--
-- Name: tracks tracks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tracks
    ADD CONSTRAINT tracks_pkey PRIMARY KEY (id);


--
-- Name: tracks tracks_track_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tracks
    ADD CONSTRAINT tracks_track_id_key UNIQUE (track_id);


--
-- Name: workflow_state workflow_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_state
    ADD CONSTRAINT workflow_state_pkey PRIMARY KEY (workflow_id);


--
-- Name: ux_tracks_identity; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_tracks_identity ON public.tracks USING btree (artist_id, album_id, title);


--
-- Name: artists artists_insert_trigger; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER artists_insert_trigger AFTER INSERT ON public.artists FOR EACH ROW EXECUTE FUNCTION public.on_artists_insert();



--
-- Name: track_plays track_plays_insert_trigger; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER track_plays_insert_trigger AFTER INSERT ON public.track_plays FOR EACH ROW EXECUTE FUNCTION public.notify_track_play_insert();


--
-- Name: tracks tracks_insert_trigger; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER tracks_insert_trigger AFTER INSERT ON public.tracks FOR EACH ROW EXECUTE FUNCTION public.on_tracks_insert();


--
-- Name: workflow_state trg_notify_workflow_progress; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_notify_workflow_progress AFTER UPDATE ON public.workflow_state FOR EACH ROW EXECUTE FUNCTION public.notify_workflow_progress();


--
-- Name: albums albums_artist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.albums
    ADD CONSTRAINT albums_artist_id_fkey FOREIGN KEY (artist_id) REFERENCES public.artists(id) ON DELETE CASCADE;


--
-- Name: artist_genres artist_genres_artist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artist_genres
    ADD CONSTRAINT artist_genres_artist_id_fkey FOREIGN KEY (artist_id) REFERENCES public.artists(id) ON DELETE CASCADE;


--
-- Name: artist_genres artist_genres_genre_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artist_genres
    ADD CONSTRAINT artist_genres_genre_id_fkey FOREIGN KEY (genre_id) REFERENCES public.genres(id) ON DELETE CASCADE;


--
-- Name: track_plays track_plays_track_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.track_plays
    ADD CONSTRAINT track_plays_track_id_fkey FOREIGN KEY (track_id) REFERENCES public.tracks(id) ON DELETE CASCADE;


--
-- Name: tracks tracks_album_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tracks
    ADD CONSTRAINT tracks_album_id_fkey FOREIGN KEY (album_id) REFERENCES public.albums(id) ON DELETE CASCADE;


--
-- Name: tracks tracks_artist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tracks
    ADD CONSTRAINT tracks_artist_id_fkey FOREIGN KEY (artist_id) REFERENCES public.artists(id) ON DELETE CASCADE;


--
-- Name: artists workflow_id_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artists
    ADD CONSTRAINT workflow_id_fk FOREIGN KEY (workflow_id) REFERENCES public.workflow_state(workflow_id);


--
-- Name: track_plays workflow_id_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.track_plays
    ADD CONSTRAINT workflow_id_fk FOREIGN KEY (workflow_id) REFERENCES public.workflow_state(workflow_id);


--
-- Name: tracks workflow_id_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tracks
    ADD CONSTRAINT workflow_id_fk FOREIGN KEY (workflow_id) REFERENCES public.workflow_state(workflow_id);


--
-- PostgreSQL database dump complete
--

\unrestrict sOfgedFv6wEyNRLLqhgxcRozFWribELaNyYcwdG7PVBphoRlhOcXzBizsnSiemo

