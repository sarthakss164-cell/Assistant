"""
Unit and integration tests for Phase 8.2: Deterministic Music Command and Assistant Integration.
Verifies deterministic music intent routing (songs, playlists, stop), playlist validation,
empty/ambiguous query rejection, gateway bypass, non-blocking playback dispatch,
graceful dependency degradation, and safe assistant shutdown cleanup.
All tests use mocks; no real streaming or network requests are executed.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from core.router import CommandRouter, IntentType, CommandIntent
from core.state_machine import SessionStateMachine, SessionState
from core.assistant import LightAssistant
from core.coe_gateway import CoeGatewayClient, GatewayResponse, GatewayStatus
from config.settings import DEFAULT_PLAYLISTS


class TestPhase82MusicRouting(unittest.TestCase):
    """Verifies deterministic routing for music commands."""

    def setUp(self):
        self.sm = SessionStateMachine()
        self.mock_gateway = MagicMock(spec=CoeGatewayClient)
        self.mock_gateway.is_configured = True
        self.router = CommandRouter(gateway_client=self.mock_gateway)

    def test_1_deterministic_routing_of_supported_song_requests(self):
        """Verifies single song requests with wake prefix in WAITING and unprefixed in ACTIVE."""
        # 1. Prefixed variations in WAITING_FOR_ACTIVATION
        examples = [
            ("Light, Zaalima song play karo.", "zaalima"),
            ("Light, play Zaalima.", "zaalima"),
            ("Light, play song Zaalima", "zaalima"),
            ("Light, Zaalima gaana play karo", "zaalima"),
            ("Light, palat tera hero idhar hai song play karo", "palat tera hero idhar hai"),
            ("Light, play palat tera hero idhar hai", "palat tera hero idhar hai"),
        ]
        for utterance, expected_query in examples:
            intent = self.router.route(utterance, self.sm.current_state)
            self.assertEqual(intent.intent_type, IntentType.PLAY_SONG, f"Failed on '{utterance}'")
            self.assertEqual(intent.payload.get("query"), expected_query)
            self.assertTrue(intent.payload.get("is_valid"))
            self.assertTrue(intent.should_activate_session)

        # 2. Unprefixed in ACTIVE_SESSION
        self.sm.activate_session()
        active_examples = [
            ("Zaalima song play karo", "zaalima"),
            ("play Zaalima", "zaalima"),
            ("zaalima play karo", "zaalima"),
            ("zaalima chalao", "zaalima"),
            ("play palat tera hero idhar hai", "palat tera hero idhar hai"),
        ]
        for utterance, expected_query in active_examples:
            intent = self.router.route(utterance, self.sm.current_state)
            self.assertEqual(intent.intent_type, IntentType.PLAY_SONG, f"Failed on active '{utterance}'")
            self.assertEqual(intent.payload.get("query"), expected_query)
            self.assertTrue(intent.payload.get("is_valid"))

    def test_2_deterministic_routing_of_supported_playlist_requests(self):
        """Verifies named playlist requests resolved against DEFAULT_PLAYLISTS."""
        # 1. In WAITING_FOR_ACTIVATION
        playlist_examples = [
            ("Light, Hindi playlist play karo.", "hindi"),
            ("Light, story playlist play karo.", "story"),
            ("Light, play Hindi playlist", "hindi"),
            ("Light, play story playlist", "story"),
            ("Light, start hindi playlist", "hindi"),
            ("Light, hindi playlist chalao", "hindi"),
        ]
        for utterance, expected_pl in playlist_examples:
            intent = self.router.route(utterance, self.sm.current_state)
            self.assertEqual(intent.intent_type, IntentType.PLAY_PLAYLIST, f"Failed on '{utterance}'")
            self.assertEqual(intent.payload.get("playlist_name"), expected_pl)
            self.assertTrue(intent.payload.get("is_valid"))
            self.assertTrue(intent.should_activate_session)

        # 2. In ACTIVE_SESSION
        self.sm.activate_session()
        active_playlists = [
            ("hindi playlist play karo", "hindi"),
            ("play story playlist", "story"),
            ("hindi playlist", "hindi"),
            ("story playlist", "story"),
        ]
        for utterance, expected_pl in active_playlists:
            intent = self.router.route(utterance, self.sm.current_state)
            self.assertEqual(intent.intent_type, IntentType.PLAY_PLAYLIST, f"Failed on active '{utterance}'")
            self.assertEqual(intent.payload.get("playlist_name"), expected_pl)
            self.assertTrue(intent.payload.get("is_valid"))

    def test_3_stop_music_intent_routing(self):
        """Verifies stop music variations route to STOP_MUSIC while standalone stop remains EXIT."""
        stop_variations = [
            "Light, stop music.",
            "Light, gaana band karo.",
            "Light, music stop karo",
            "Light, music band karo",
            "Light, stop playback",
            "Light, gaana roko",
            "Light, music roko",
        ]
        for utterance in stop_variations:
            intent = self.router.route(utterance, self.sm.current_state)
            self.assertEqual(intent.intent_type, IntentType.STOP_MUSIC, f"Failed on '{utterance}'")

        self.sm.activate_session()
        active_stops = [
            "stop music",
            "gaana band karo",
            "music stop",
            "music stop karo",
            "music band karo",
            "stop playback",
            "playback stop",
            "gaana roko",
        ]
        for utterance in active_stops:
            intent = self.router.route(utterance, self.sm.current_state)
            self.assertEqual(intent.intent_type, IntentType.STOP_MUSIC, f"Failed on active '{utterance}'")

        # In contrast, standalone exit commands like "stop" or "exit" must route to EXIT
        exit_intent = self.router.route("stop", self.sm.current_state)
        self.assertEqual(exit_intent.intent_type, IntentType.EXIT)

    def test_4_unknown_playlist_rejection(self):
        """Verifies unknown or empty playlist requests are rejected deterministically."""
        # Unknown playlist names (note: 'english' is now a valid configured playlist in D4.2)
        unknowns = [
            "Light, play rock playlist",
            "Light, punjabi playlist play karo",
            "Light, jazz playlist play karo",
        ]
        for utterance in unknowns:
            intent = self.router.route(utterance, self.sm.current_state)
            self.assertEqual(intent.intent_type, IntentType.PLAY_PLAYLIST, f"Failed on '{utterance}'")
            self.assertFalse(intent.payload.get("is_valid"))
            self.assertEqual(intent.payload.get("error"), "unknown_playlist")

        # Empty playlist requests
        empty_playlists = [
            "Light, play playlist",
            "Light, playlist play karo",
        ]
        for utterance in empty_playlists:
            intent = self.router.route(utterance, self.sm.current_state)
            self.assertEqual(intent.intent_type, IntentType.PLAY_PLAYLIST, f"Failed on '{utterance}'")
            self.assertFalse(intent.payload.get("is_valid"))
            self.assertEqual(intent.payload.get("error"), "empty_playlist")

    def test_5_empty_and_ambiguous_song_query_rejection(self):
        """Verifies empty or ambiguous song queries are safely rejected."""
        ambiguous = [
            "Light, play",
            "Light, play song",
            "Light, gaana play karo",
            "Light, gaana chalao",
            "Light, play music",
            "Light, play something",
            "Light, koi gaana play karo",
            "Light, play anything",
        ]
        for utterance in ambiguous:
            intent = self.router.route(utterance, self.sm.current_state)
            self.assertEqual(intent.intent_type, IntentType.PLAY_SONG, f"Failed on '{utterance}'")
            self.assertFalse(intent.payload.get("is_valid"))
            self.assertIn(intent.payload.get("error"), ("empty_query", "ambiguous_query"))

    def test_6_music_commands_do_not_route_through_ai_gateway(self):
        """Verifies music commands (valid and invalid) 100% bypass the AI gateway."""
        commands = [
            "Light, Zaalima song play karo.",
            "Light, play Zaalima.",
            "Light, Hindi playlist play karo.",
            "Light, story playlist play karo.",
            "Light, stop music.",
            "Light, gaana band karo.",
            "Light, play rock playlist",
            "Light, play song",
            "Light, play something",
        ]
        for cmd in commands:
            self.router.route(cmd, self.sm.current_state)

        # Gateway must not have received any calls
        self.mock_gateway.complete.assert_not_called()

        # Non-music questions DO fall back to gateway
        self.mock_gateway.complete.return_value = GatewayResponse(
            status=GatewayStatus.SUCCESS,
            raw_content='{"intent": "CONVERSATION", "voice_response": "AI is artificial intelligence."}',
        )
        qa_intent = self.router.route("Light, explain artificial intelligence in simple words", self.sm.current_state)
        self.assertEqual(qa_intent.intent_type, IntentType.CONVERSATION)
        self.mock_gateway.complete.assert_called_once()


class TestPhase82AssistantIntegration(unittest.TestCase):
    """Verifies assistant integration with the music player engine."""

    def setUp(self):
        self.mock_music_player = MagicMock()
        self.mock_music_player.is_available = True
        self.mock_music_player.play_song.return_value = (True, "Playing")
        self.mock_music_player.play_playlist.return_value = (True, "Playing playlist")
        self.mock_music_player.stop.return_value = True

        self.mock_tts = MagicMock()
        self.mock_tts.speak.return_value = True

        self.assistant = LightAssistant(
            music_player=self.mock_music_player,
            tts=self.mock_tts,
        )

    def tearDown(self):
        if hasattr(self, "assistant"):
            self.assistant._shutdown_internal(farewell_message="")

    def test_7_music_playback_dispatch_does_not_block_assistant_loop(self):
        """Verifies play_song and play_playlist dispatch non-blockingly."""
        intent = CommandIntent(
            IntentType.PLAY_SONG,
            payload={"query": "zaalima", "is_valid": True},
        )
        start_time = time.time()
        res = self.assistant.handle_intent(intent)
        elapsed = time.time() - start_time

        self.assertTrue(res)
        self.assertLess(elapsed, 0.1, "handle_intent blocked for too long on play_song")

        # Allow concurrent worker slice to invoke music_player
        time.sleep(0.05)
        self.mock_music_player.play_song.assert_called_once_with("zaalima")
        self.mock_tts.speak.assert_called()
        ack = self.mock_tts.speak.call_args[0][0]
        self.assertIn("zaalima", ack.lower())
        self.assertIn("play kar rahi hoon", ack.lower())

    def test_7b_playlist_dispatch_does_not_block_assistant_loop(self):
        """Verifies play_playlist dispatches non-blockingly with female Hinglish ack."""
        intent = CommandIntent(
            IntentType.PLAY_PLAYLIST,
            payload={"playlist_name": "hindi", "is_valid": True},
        )
        start_time = time.time()
        res = self.assistant.handle_intent(intent)
        elapsed = time.time() - start_time

        self.assertTrue(res)
        self.assertLess(elapsed, 0.1, "handle_intent blocked for too long on play_playlist")

        time.sleep(0.05)
        self.mock_music_player.play_playlist.assert_called_once_with("hindi")
        ack = self.mock_tts.speak.call_args[0][0]
        self.assertIn("hindi", ack.lower())
        self.assertIn("playlist play kar rahi hoon", ack.lower())

    def test_8_stop_clears_queued_playback_through_music_engine(self):
        """Verifies STOP_MUSIC intent triggers stop() on the music player."""
        intent = CommandIntent(IntentType.STOP_MUSIC)
        res = self.assistant.handle_intent(intent)

        self.assertTrue(res)
        self.mock_music_player.stop.assert_called_once()
        ack = self.mock_tts.speak.call_args[0][0]
        self.assertIn("band kar diya", ack.lower())

    def test_9_missing_vlc_or_dependency_fails_gracefully(self):
        """Verifies unavailable music player results in friendly TTS rather than crashing."""
        self.mock_music_player.is_available = False

        intent_song = CommandIntent(
            IntentType.PLAY_SONG,
            payload={"query": "zaalima", "is_valid": True},
        )
        res1 = self.assistant.handle_intent(intent_song)
        self.assertTrue(res1)
        self.mock_music_player.play_song.assert_not_called()
        self.assertIn("available nahi", self.mock_tts.speak.call_args[0][0].lower())

        intent_pl = CommandIntent(
            IntentType.PLAY_PLAYLIST,
            payload={"playlist_name": "hindi", "is_valid": True},
        )
        res2 = self.assistant.handle_intent(intent_pl)
        self.assertTrue(res2)
        self.mock_music_player.play_playlist.assert_not_called()
        self.assertIn("available nahi", self.mock_tts.speak.call_args[0][0].lower())

    def test_10_assistant_shutdown_safely_cleans_up_music_player(self):
        """Verifies assistant shutdown safely invokes music_player.shutdown()."""
        exit_intent = CommandIntent(IntentType.EXIT)
        # Activate session first so exit is recognized
        self.assistant.state_machine.activate_session()
        res = self.assistant.handle_intent(exit_intent)

        self.assertFalse(res)
        self.mock_music_player.shutdown.assert_called_once()

    def test_11_unknown_playlist_and_empty_query_assistant_responses(self):
        """Verifies assistant handles unknown playlist and empty song queries politely."""
        # 1. Unknown playlist
        intent_unknown_pl = CommandIntent(
            IntentType.PLAY_PLAYLIST,
            payload={"playlist_name": "rock", "error": "unknown_playlist", "is_valid": False},
        )
        self.assistant.handle_intent(intent_unknown_pl)
        self.mock_music_player.play_playlist.assert_not_called()
        ack_pl = self.mock_tts.speak.call_args[0][0]
        self.assertIn("rock", ack_pl)
        self.assertIn("hindi aur story", ack_pl.lower())

        # 2. Empty song query
        intent_empty_song = CommandIntent(
            IntentType.PLAY_SONG,
            payload={"query": "", "error": "empty_query", "is_valid": False},
        )
        self.assistant.handle_intent(intent_empty_song)
        self.mock_music_player.play_song.assert_not_called()
        ack_song = self.mock_tts.speak.call_args[0][0]
        self.assertIn("kaunsa gaana", ack_song.lower())

    def test_12_non_music_conversational_text_not_hijacked(self):
        """Verifies conversational queries or queries with 'play' in context are not hijacked by music."""
        router = CommandRouter()
        sm = SessionStateMachine()
        sm.activate_session()

        # "play machine learning on youtube" -> YouTube search
        yt_intent = router.route("play machine learning on YouTube", sm.current_state)
        self.assertEqual(yt_intent.intent_type, IntentType.SEARCH_YOUTUBE)
        self.assertEqual(yt_intent.payload.get("query"), "machine learning")

        # Questions containing play: "can you play chess?"
        q_intent = router.route("can you play chess?", sm.current_state)
        self.assertNotEqual(q_intent.intent_type, IntentType.PLAY_SONG)
        self.assertNotEqual(q_intent.intent_type, IntentType.PLAY_PLAYLIST)
