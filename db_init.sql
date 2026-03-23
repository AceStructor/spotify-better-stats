--
-- PostgreSQL database dump
--

\restrict GCTiO97OWGFhPeIyYOM6kreN0zzWr9Mbv4pd7y1drGvOEsDcHUMYQ3hn9dAwW0l

-- Dumped from database version 16.11 (Debian 16.11-1.pgdg13+1)
-- Dumped by pg_dump version 17.7

-- Started on 2026-03-22 23:18:17

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 2 (class 3079 OID 16385)
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- TOC entry 3570 (class 0 OID 0)
-- Dependencies: 2
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- TOC entry 925 (class 1247 OID 25085)
-- Name: genre_load_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.genre_load_status AS ENUM (
    'none',
    'loading',
    'done',
    'error'
);


--
-- TOC entry 270 (class 1255 OID 16422)
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


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 227 (class 1259 OID 24753)
-- Name: album_tracks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.album_tracks (
    album_id bigint NOT NULL,
    track_id bigint NOT NULL,
    track_number integer DEFAULT 0,
    disc_number integer DEFAULT 1
);


--
-- TOC entry 216 (class 1259 OID 16426)
-- Name: albums; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.albums (
    id integer NOT NULL,
    title text NOT NULL,
    release_date date,
    created_at timestamp with time zone DEFAULT now(),
    mbid uuid
);


--
-- TOC entry 217 (class 1259 OID 16432)
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
-- TOC entry 3571 (class 0 OID 0)
-- Dependencies: 217
-- Name: albums_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--


--
-- TOC entry 229 (class 1259 OID 24861)
-- Name: artist_albums; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.artist_albums (
    artist_id bigint NOT NULL,
    album_id bigint NOT NULL
);


--
-- TOC entry 218 (class 1259 OID 16433)
-- Name: artist_genres; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.artist_genres (
    artist_id integer NOT NULL,
    genre_id integer NOT NULL
);


--
-- TOC entry 228 (class 1259 OID 24846)
-- Name: artist_tracks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.artist_tracks (
    artist_id bigint NOT NULL,
    track_id bigint NOT NULL
);


--
-- TOC entry 219 (class 1259 OID 16436)
-- Name: artists; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.artists (
    id integer NOT NULL,
    name text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    genre_status public.genre_load_status DEFAULT 'none'::public.genre_load_status NOT NULL
);


--
-- TOC entry 220 (class 1259 OID 16442)
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
-- TOC entry 3572 (class 0 OID 0)
-- Dependencies: 220
-- Name: artists_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.artists_id_seq OWNED BY public.artists.id;


--
-- TOC entry 221 (class 1259 OID 16443)
-- Name: genres; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.genres (
    id integer NOT NULL,
    name text NOT NULL
);


--
-- TOC entry 222 (class 1259 OID 16448)
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
-- TOC entry 3573 (class 0 OID 0)
-- Dependencies: 222
-- Name: genres_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.genres_id_seq OWNED BY public.genres.id;


--
-- TOC entry 223 (class 1259 OID 16449)
-- Name: track_plays; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.track_plays (
    id integer NOT NULL,
    track_id integer NOT NULL,
    played_at timestamp with time zone NOT NULL,
    skipped boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    user_id bigint
);


--
-- TOC entry 230 (class 1259 OID 24878)
-- Name: track_plays_backup; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.track_plays_backup (
    played_at timestamp with time zone,
    skipped boolean,
    track_title text,
    artist_names text,
    id bigint NOT NULL
);


--
-- TOC entry 231 (class 1259 OID 25094)
-- Name: track_plays_backup_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.track_plays_backup_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 3574 (class 0 OID 0)
-- Dependencies: 231
-- Name: track_plays_backup_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.track_plays_backup_id_seq OWNED BY public.track_plays_backup.id;


--
-- TOC entry 224 (class 1259 OID 16454)
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
-- TOC entry 3575 (class 0 OID 0)
-- Dependencies: 224
-- Name: track_plays_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.track_plays_id_seq OWNED BY public.track_plays.id;


--
-- TOC entry 225 (class 1259 OID 16455)
-- Name: tracks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tracks (
    id integer NOT NULL,
    title text NOT NULL,
    duration_ms integer,
    created_at timestamp with time zone DEFAULT now(),
    youtube_code text,
    download_status text DEFAULT 'none'::text NOT NULL,
    file_path text,
    audio_format text,
    downloaded_at timestamp with time zone,
    download_error text,
    mbid uuid,
    CONSTRAINT tracks_download_status_check CHECK ((download_status = ANY (ARRAY['none'::text, 'pending'::text, 'queued'::text, 'downloading'::text, 'done'::text, 'error'::text])))
);


--
-- TOC entry 226 (class 1259 OID 16463)
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
-- TOC entry 3576 (class 0 OID 0)
-- Dependencies: 226
-- Name: tracks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tracks_id_seq OWNED BY public.tracks.id;


--
-- TOC entry 233 (class 1259 OID 25106)
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id bigint NOT NULL,
    username text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- TOC entry 232 (class 1259 OID 25105)
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 3577 (class 0 OID 0)
-- Dependencies: 232
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- TOC entry 3354 (class 2604 OID 16474)
-- Name: albums id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.albums ALTER COLUMN id SET DEFAULT nextval('public.albums_id_seq'::regclass);


--
-- TOC entry 3356 (class 2604 OID 16475)
-- Name: artists id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artists ALTER COLUMN id SET DEFAULT nextval('public.artists_id_seq'::regclass);


--
-- TOC entry 3359 (class 2604 OID 16476)
-- Name: genres id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.genres ALTER COLUMN id SET DEFAULT nextval('public.genres_id_seq'::regclass);


--
-- TOC entry 3360 (class 2604 OID 16477)
-- Name: track_plays id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.track_plays ALTER COLUMN id SET DEFAULT nextval('public.track_plays_id_seq'::regclass);


--
-- TOC entry 3368 (class 2604 OID 25095)
-- Name: track_plays_backup id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.track_plays_backup ALTER COLUMN id SET DEFAULT nextval('public.track_plays_backup_id_seq'::regclass);


--
-- TOC entry 3363 (class 2604 OID 16478)
-- Name: tracks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tracks ALTER COLUMN id SET DEFAULT nextval('public.tracks_id_seq'::regclass);


--
-- TOC entry 3369 (class 2604 OID 25109)
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- TOC entry 3396 (class 2606 OID 24759)
-- Name: album_tracks album_tracks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.album_tracks
    ADD CONSTRAINT album_tracks_pkey PRIMARY KEY (album_id, track_id);


--
-- TOC entry 3373 (class 2606 OID 16482)
-- Name: albums albums_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.albums
    ADD CONSTRAINT albums_pkey PRIMARY KEY (id);


--
-- TOC entry 3403 (class 2606 OID 24865)
-- Name: artist_albums artist_albums_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artist_albums
    ADD CONSTRAINT artist_albums_pkey PRIMARY KEY (artist_id, album_id);


--
-- TOC entry 3376 (class 2606 OID 16484)
-- Name: artist_genres artist_genres_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artist_genres
    ADD CONSTRAINT artist_genres_pkey PRIMARY KEY (artist_id, genre_id);


--
-- TOC entry 3400 (class 2606 OID 24850)
-- Name: artist_tracks artist_tracks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artist_tracks
    ADD CONSTRAINT artist_tracks_pkey PRIMARY KEY (artist_id, track_id);


--
-- TOC entry 3378 (class 2606 OID 16486)
-- Name: artists artists_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artists
    ADD CONSTRAINT artists_name_key UNIQUE (name);


--
-- TOC entry 3380 (class 2606 OID 16488)
-- Name: artists artists_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artists
    ADD CONSTRAINT artists_pkey PRIMARY KEY (id);


--
-- TOC entry 3383 (class 2606 OID 16490)
-- Name: genres genres_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.genres
    ADD CONSTRAINT genres_name_key UNIQUE (name);


--
-- TOC entry 3385 (class 2606 OID 16492)
-- Name: genres genres_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.genres
    ADD CONSTRAINT genres_pkey PRIMARY KEY (id);


--
-- TOC entry 3406 (class 2606 OID 25097)
-- Name: track_plays_backup track_plays_backup_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.track_plays_backup
    ADD CONSTRAINT track_plays_backup_pkey PRIMARY KEY (id);


--
-- TOC entry 3387 (class 2606 OID 16494)
-- Name: track_plays track_plays_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.track_plays
    ADD CONSTRAINT track_plays_pkey PRIMARY KEY (id);


--
-- TOC entry 3389 (class 2606 OID 16496)
-- Name: track_plays track_plays_track_id_played_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.track_plays
    ADD CONSTRAINT track_plays_track_id_played_at_key UNIQUE (track_id, played_at);


--
-- TOC entry 3391 (class 2606 OID 25124)
-- Name: track_plays track_plays_unique_play; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.track_plays
    ADD CONSTRAINT track_plays_unique_play UNIQUE (user_id, track_id, played_at);


--
-- TOC entry 3393 (class 2606 OID 16500)
-- Name: tracks tracks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tracks
    ADD CONSTRAINT tracks_pkey PRIMARY KEY (id);


--
-- TOC entry 3408 (class 2606 OID 25114)
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- TOC entry 3410 (class 2606 OID 25116)
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- TOC entry 3397 (class 1259 OID 24771)
-- Name: idx_album_tracks_album; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_album_tracks_album ON public.album_tracks USING btree (album_id);


--
-- TOC entry 3398 (class 1259 OID 24772)
-- Name: idx_album_tracks_track; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_album_tracks_track ON public.album_tracks USING btree (track_id);


--
-- TOC entry 3404 (class 1259 OID 24877)
-- Name: idx_artist_albums_album; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artist_albums_album ON public.artist_albums USING btree (album_id);


--
-- TOC entry 3401 (class 1259 OID 24876)
-- Name: idx_artist_tracks_track; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_artist_tracks_track ON public.artist_tracks USING btree (track_id);


--
-- TOC entry 3374 (class 1259 OID 24920)
-- Name: uniq_albums_mbid; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uniq_albums_mbid ON public.albums USING btree (mbid);


--
-- TOC entry 3381 (class 1259 OID 24919)
-- Name: uniq_artist_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uniq_artist_name ON public.artists USING btree (name);


--
-- TOC entry 3394 (class 1259 OID 24921)
-- Name: uniq_tracks_mbid; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uniq_tracks_mbid ON public.tracks USING btree (mbid);


--
-- TOC entry 3421 (class 2620 OID 16507)
-- Name: track_plays track_plays_insert_trigger; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER track_plays_insert_trigger AFTER INSERT ON public.track_plays FOR EACH ROW EXECUTE FUNCTION public.notify_track_play_insert();


--
-- TOC entry 3419 (class 2606 OID 24871)
-- Name: artist_albums artist_albums_album_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artist_albums
    ADD CONSTRAINT artist_albums_album_id_fkey FOREIGN KEY (album_id) REFERENCES public.albums(id) ON DELETE CASCADE;


--
-- TOC entry 3420 (class 2606 OID 24866)
-- Name: artist_albums artist_albums_artist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artist_albums
    ADD CONSTRAINT artist_albums_artist_id_fkey FOREIGN KEY (artist_id) REFERENCES public.artists(id) ON DELETE CASCADE;


--
-- TOC entry 3411 (class 2606 OID 16515)
-- Name: artist_genres artist_genres_artist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artist_genres
    ADD CONSTRAINT artist_genres_artist_id_fkey FOREIGN KEY (artist_id) REFERENCES public.artists(id) ON DELETE CASCADE;


--
-- TOC entry 3412 (class 2606 OID 16520)
-- Name: artist_genres artist_genres_genre_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artist_genres
    ADD CONSTRAINT artist_genres_genre_id_fkey FOREIGN KEY (genre_id) REFERENCES public.genres(id) ON DELETE CASCADE;


--
-- TOC entry 3417 (class 2606 OID 24851)
-- Name: artist_tracks artist_tracks_artist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artist_tracks
    ADD CONSTRAINT artist_tracks_artist_id_fkey FOREIGN KEY (artist_id) REFERENCES public.artists(id) ON DELETE CASCADE;


--
-- TOC entry 3418 (class 2606 OID 24856)
-- Name: artist_tracks artist_tracks_track_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artist_tracks
    ADD CONSTRAINT artist_tracks_track_id_fkey FOREIGN KEY (track_id) REFERENCES public.tracks(id) ON DELETE CASCADE;


--
-- TOC entry 3415 (class 2606 OID 24760)
-- Name: album_tracks fk_album_tracks_album; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.album_tracks
    ADD CONSTRAINT fk_album_tracks_album FOREIGN KEY (album_id) REFERENCES public.albums(id) ON DELETE CASCADE;


--
-- TOC entry 3416 (class 2606 OID 24765)
-- Name: album_tracks fk_album_tracks_track; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.album_tracks
    ADD CONSTRAINT fk_album_tracks_track FOREIGN KEY (track_id) REFERENCES public.tracks(id) ON DELETE CASCADE;


--
-- TOC entry 3413 (class 2606 OID 16525)
-- Name: track_plays track_plays_track_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.track_plays
    ADD CONSTRAINT track_plays_track_id_fkey FOREIGN KEY (track_id) REFERENCES public.tracks(id) ON DELETE CASCADE;


--
-- TOC entry 3414 (class 2606 OID 25118)
-- Name: track_plays track_plays_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.track_plays
    ADD CONSTRAINT track_plays_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


-- Completed on 2026-03-22 23:18:17

--
-- PostgreSQL database dump complete
--

\unrestrict GCTiO97OWGFhPeIyYOM6kreN0zzWr9Mbv4pd7y1drGvOEsDcHUMYQ3hn9dAwW0l

