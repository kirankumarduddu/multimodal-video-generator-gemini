/* Guide data: defaults, the kettle-and-kite example answers, voices and look presets. */
(function () {
  'use strict';

  var D = {};

  D.REPO_URL = 'https://github.com/kirankumarduddu/multimodal-video-generator-gemini';
  D.CLONE_URL = D.REPO_URL + '.git';
  D.REPO_DIR = 'multimodal-video-generator-gemini';

  D.MODEL_DEFAULTS = {
    'story.provider': 'gemini',
    'story.gemini.model': 'gemini-3.5-flash',
    'story.gemini.location': 'global',
    'story.openai.model': 'gpt-5',
    'story.openai.base_url': 'https://api.openai.com/v1',
    'story.openai.api_key_env': 'OPENAI_API_KEY',
    'story.anthropic.model': 'claude-sonnet-5',
    'story.anthropic.api_key_env': 'ANTHROPIC_API_KEY',
    'video.provider': 'veo',
    'video.veo.model': 'veo-3.1-generate-001',
    'video.omni.model': 'gemini-omni-1.1-flash-preview',
    'video.omni.location': 'global',
    'video.resolution': '1080p',
    'video.generate_audio': 'false',
    'image.model': 'gemini-3-pro-image',
    'image.location': 'global',
    'tts.model': 'gemini-3.1-flash-tts-preview',
    'tts.location': 'global',
    'music.model': 'lyria-3-pro-preview',
    'music.location': 'global',
    'limits.parallel': '3',
    'gcp.region': 'us-central1'
  };

  D.BRAND_DEFAULTS = {
    'brand.name': '',
    'brand.tagline': '',
    'brand.colors.background': '#14302B',
    'brand.colors.surface': '#1E4A42',
    'brand.colors.primary': '#E9B44C',
    'brand.colors.accent': '#F6E7C8',
    'brand.colors.text': '#FFF9EE',
    'brand.colors.muted': '#BFD6CF',
    'brand.fonts.heading': 'Inter',
    'brand.fonts.body': 'Inter',
    'brand.logo': '',
    'brand.look': '',
    'brand.voice.name': 'Sulafat',
    'brand.voice.direction': '',
    'brand.rules': ''
  };

  D.BRIEF_DEFAULTS = {
    'brief.purpose': '',
    'brief.audience': '',
    'brief.length': '60',
    'brief.lengthCustom': '45',
    'brief.aspect': '16:9',
    'brief.language': 'English',
    'brief.key_message': '',
    'brief.story_angle': '',
    'brief.beats': '',
    'brief.proof_points': '',
    'brief.quotes': '',
    'brief.call_to_action': '',
    'brief.characters': '',
    'brief.settings': '',
    'brief.mood': '',
    'brief.music_mood': '',
    'brief.screenshots': '',
    'brief.must_include': '',
    'brief.must_avoid': ''
  };

  D.DEFAULTS = Object.assign({
    'os': /Win/i.test(navigator.platform || navigator.userAgent) ? 'windows' : 'unix',
    'project.dir': 'my-film',
    'gcp.project': '',
    'gcp.email': '',
    'gcp.bucket': '',
    'story.text': ''
  }, D.MODEL_DEFAULTS, D.BRAND_DEFAULTS, D.BRIEF_DEFAULTS);

  // The examples/kettle-and-kite answers.
  D.EXAMPLE = {
    brand: {
      'brand.name': 'Kettle & Kite',
      'brand.tagline': 'Your usual, ready when you are.',
      'brand.colors.background': '#14302B',
      'brand.colors.surface': '#1E4A42',
      'brand.colors.primary': '#E9B44C',
      'brand.colors.accent': '#F6E7C8',
      'brand.colors.text': '#FFF9EE',
      'brand.colors.muted': '#BFD6CF',
      'brand.fonts.heading': 'Fraunces',
      'brand.fonts.body': 'Inter',
      'brand.logo': '',
      'brand.look': 'Photoreal, cinematic, natural window light, warm amber and deep green color grade, soft film grain, shallow depth of field, calm handheld camera',
      'brand.voice.name': 'Sulafat',
      'brand.voice.direction': 'Read this as the warm, unhurried narrator of a small, premium brand film. Natural pauses, smiling voice, no hype.',
      'brand.rules': [
        'No logos, brand names or readable text in AI-generated footage; words live on cards',
        'Only invented, fictional people'
      ].join('\n')
    },
    brief: {
      'brief.purpose': 'Launch trailer for a new ordering app',
      'brief.audience': "Regulars and neighbours of a small tea house, on social media and the shop's screen",
      'brief.length': '60',
      'brief.aspect': '16:9',
      'brief.language': 'English',
      'brief.key_message': 'Your usual, ready when you walk in, without the queue.',
      'brief.story_angle': 'A busy morning in a neighbourhood tea house, and the small ritual the app gives back.',
      'brief.beats': [
        "The morning rush, and regulars who don't have time to wait",
        'Introducing the Kettle & Kite app',
        'Order your usual in two taps, pay ahead, pick up at the shelf',
        'Seasonal blends and a loyalty stamp on every cup',
        'Back to what the shop is about, people and tea'
      ].join('\n'),
      'brief.proof_points': ['Opens 7 days a week from 7 AM', 'Orders are ready in about 5 minutes'].join('\n'),
      'brief.quotes': '',
      'brief.call_to_action': 'Download the app and get your first pot on us',
      'brief.characters': [
        'The owner, a woman in her 50s who knows every regular',
        'A regular, a young nurse coming off a night shift'
      ].join('\n'),
      'brief.settings': [
        'A small, warm tea house with wooden shelves of tea tins and big windows',
        'A rainy street outside at early morning'
      ].join('\n'),
      'brief.mood': 'Warm, calm, human, a little playful',
      'brief.music_mood': 'Gentle acoustic guitar and soft piano, rising to a bright, hopeful close',
      'brief.screenshots': '',
      'brief.must_include': 'The shop name on the title and end card',
      'brief.must_avoid': ["Any real person's likeness", 'Prices or discounts other than the call to action'].join('\n')
    }
  };

  // Gemini TTS prebuilt voices with their style hints.
  D.VOICES = [
    ['Zephyr', 'bright'], ['Puck', 'upbeat'], ['Charon', 'informative'], ['Kore', 'firm'], ['Fenrir', 'excitable'],
    ['Leda', 'youthful'], ['Orus', 'firm'], ['Aoede', 'breezy'], ['Callirrhoe', 'easy-going'], ['Autonoe', 'bright'],
    ['Enceladus', 'breathy'], ['Iapetus', 'clear'], ['Umbriel', 'easy-going'], ['Algieba', 'smooth'], ['Despina', 'smooth'],
    ['Erinome', 'clear'], ['Algenib', 'gravelly'], ['Rasalgethi', 'informative'], ['Laomedeia', 'upbeat'], ['Achernar', 'soft'],
    ['Alnilam', 'firm'], ['Schedar', 'even'], ['Gacrux', 'mature'], ['Pulcherrima', 'forward'], ['Achird', 'friendly'],
    ['Zubenelgenubi', 'casual'], ['Vindemiatrix', 'gentle'], ['Sadachbia', 'lively'], ['Sadaltager', 'knowledgeable'], ['Sulafat', 'warm']
  ];

  D.LOOKS = {
    warm: 'Photoreal, documentary style, natural window light, warm color grade, soft film grain, gentle handheld camera, real textures and lived-in places',
    bright: 'Photoreal, bright and airy, clean soft daylight, crisp neutral color grade with gentle saturation, smooth gimbal camera, shallow depth of field',
    moody: 'Photoreal, cinematic, low-key lighting, deep shadows, teal and amber color grade, anamorphic lens feel, light haze, slow dolly moves'
  };

  window.MVG_DATA = D;
})();
