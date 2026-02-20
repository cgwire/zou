"""
Translations for email notifications. Strings are keyed by locale (e.g. en_US, fr_FR).
Emails are sent in the recipient's preferred locale when available.

Supported locales: en_US, fr_FR, es_ES, ja_JP, de_DE, nl_NL, zh_CN, pt_BR.
To add a language: copy the en_US block, change the key (e.g. de_DE) and translate
all values. Then add the 2-letter code to _normalize_locale's lang_map if desired.
"""

from zou.app import config

# Default locale used when user locale is missing or unsupported
DEFAULT_EMAIL_LOCALE = "en_US"

# Email translation strings per locale.
# Use %(name)s placeholders for interpolation.
EMAIL_TRANSLATIONS = {
    "en_US": {
        # Comment notification
        "comment_subject": "[Kitsu] %(task_status_name)s - %(author_first_name)s commented on %(task_name)s",
        "comment_title": "New Comment",
        "comment_body_with_text": """<p><strong>%(author_full_name)s</strong> wrote a comment on <a href="%(task_url)s">%(task_name)s</a> and set the status to <strong>%(task_status_name)s</strong>.</p>

<p><em>%(comment_text)s</em></p>
""",
        "comment_body_status_only": """<p><strong>%(author_full_name)s</strong> changed status of <a href="%(task_url)s">%(task_name)s</a> to <strong>%(task_status_name)s</strong>.</p>
""",
        # Mention notification
        "mention_subject": "[Kitsu] %(author_first_name)s mentioned you on %(task_name)s",
        "mention_title": "New Mention",
        "mention_body": """<p><strong>%(author_full_name)s</strong> mentioned you in a comment on <a href="%(task_url)s">%(task_name)s</a>:</p>

<p><em>%(comment_text)s</em></p>
""",
        # Assignation notification
        "assignation_subject": "[Kitsu] You were assigned to %(task_name)s",
        "assignation_title": "New Assignation",
        "assignation_body": """<p><strong>%(author_full_name)s</strong> assigned you to <a href="%(task_url)s">%(task_name)s</a>.</p>
""",
        # Reply notification
        "reply_subject": "[Kitsu] %(author_first_name)s replied on %(task_name)s",
        "reply_title": "New Reply",
        "reply_body": """<p><strong>%(author_full_name)s</strong> wrote a reply on <a href="%(task_url)s">%(task_name)s</a>.</p>

<p><em>%(reply_text)s</em></p>
""",
        # Playlist ready notification
        "playlist_subject": "[Kitsu] The playlist %(playlist_name)s in project %(project_name)s is ready for review",
        "playlist_title": "New Playlist Ready",
        "playlist_body": """<p><strong>%(author_full_name)s</strong> notifies you that playlist <a href="%(playlist_url)s">%(playlist_name)s</a> is ready for a review under %(episode_segment)sthe project %(project_name)s.</p>
""",
        "playlist_episode_segment": "the episode %(episode_name)s of ",
        "playlist_elements_count": "\n<p>%(count)s elements are listed in the playlist.</p>\n",
        "email_signature": "\n<p>Best regards,</p>\n\n<p>%(organisation_name)s Team</p>",
    },
    "fr_FR": {
        # Comment notification
        "comment_subject": "[Kitsu] %(task_status_name)s - %(author_first_name)s a commenté %(task_name)s",
        "comment_title": "Nouveau commentaire",
        "comment_body_with_text": """<p><strong>%(author_full_name)s</strong> a écrit un commentaire sur <a href="%(task_url)s">%(task_name)s</a> et a défini le statut à <strong>%(task_status_name)s</strong>.</p>

<p><em>%(comment_text)s</em></p>
""",
        "comment_body_status_only": """<p><strong>%(author_full_name)s</strong> a changé le statut de <a href="%(task_url)s">%(task_name)s</a> en <strong>%(task_status_name)s</strong>.</p>
""",
        # Mention notification
        "mention_subject": "[Kitsu] %(author_first_name)s vous a mentionné sur %(task_name)s",
        "mention_title": "Nouvelle mention",
        "mention_body": """<p><strong>%(author_full_name)s</strong> vous a mentionné dans un commentaire sur <a href="%(task_url)s">%(task_name)s</a> :</p>

<p><em>%(comment_text)s</em></p>
""",
        # Assignation notification
        "assignation_subject": "[Kitsu] Vous avez été assigné à %(task_name)s",
        "assignation_title": "Nouvelle assignation",
        "assignation_body": """<p><strong>%(author_full_name)s</strong> vous a assigné à <a href="%(task_url)s">%(task_name)s</a>.</p>
""",
        # Reply notification
        "reply_subject": "[Kitsu] %(author_first_name)s a répondu sur %(task_name)s",
        "reply_title": "Nouvelle réponse",
        "reply_body": """<p><strong>%(author_full_name)s</strong> a répondu sur <a href="%(task_url)s">%(task_name)s</a>.</p>

<p><em>%(reply_text)s</em></p>
""",
        # Playlist ready notification
        "playlist_subject": "[Kitsu] La playlist %(playlist_name)s du projet %(project_name)s est prête pour relecture",
        "playlist_title": "Nouvelle playlist prête",
        "playlist_body": """<p><strong>%(author_full_name)s</strong> vous informe que la playlist <a href="%(playlist_url)s">%(playlist_name)s</a> est prête pour relecture dans %(episode_segment)sle projet %(project_name)s.</p>
""",
        "playlist_episode_segment": "l'épisode %(episode_name)s du ",
        "playlist_elements_count": "\n<p>%(count)s éléments sont dans la playlist.</p>\n",
        "email_signature": "\n<p>Cordialement,</p>\n\n<p>L'équipe %(organisation_name)s</p>",
    },
    "es_ES": {
        # Comment notification
        "comment_subject": "[Kitsu] %(task_status_name)s - %(author_first_name)s comentó en %(task_name)s",
        "comment_title": "Nuevo comentario",
        "comment_body_with_text": """<p><strong>%(author_full_name)s</strong> escribió un comentario en <a href="%(task_url)s">%(task_name)s</a> y estableció el estado en <strong>%(task_status_name)s</strong>.</p>

<p><em>%(comment_text)s</em></p>
""",
        "comment_body_status_only": """<p><strong>%(author_full_name)s</strong> cambió el estado de <a href="%(task_url)s">%(task_name)s</a> a <strong>%(task_status_name)s</strong>.</p>
""",
        # Mention notification
        "mention_subject": "[Kitsu] %(author_first_name)s te mencionó en %(task_name)s",
        "mention_title": "Nueva mención",
        "mention_body": """<p><strong>%(author_full_name)s</strong> te mencionó en un comentario en <a href="%(task_url)s">%(task_name)s</a>:</p>

<p><em>%(comment_text)s</em></p>
""",
        # Assignation notification
        "assignation_subject": "[Kitsu] Has sido asignado a %(task_name)s",
        "assignation_title": "Nueva asignación",
        "assignation_body": """<p><strong>%(author_full_name)s</strong> te asignó a <a href="%(task_url)s">%(task_name)s</a>.</p>
""",
        # Reply notification
        "reply_subject": "[Kitsu] %(author_first_name)s respondió en %(task_name)s",
        "reply_title": "Nueva respuesta",
        "reply_body": """<p><strong>%(author_full_name)s</strong> respondió en <a href="%(task_url)s">%(task_name)s</a>.</p>

<p><em>%(reply_text)s</em></p>
""",
        # Playlist ready notification
        "playlist_subject": "[Kitsu] La playlist %(playlist_name)s del proyecto %(project_name)s está lista para revisión",
        "playlist_title": "Nueva playlist lista",
        "playlist_body": """<p><strong>%(author_full_name)s</strong> te informa que la playlist <a href="%(playlist_url)s">%(playlist_name)s</a> está lista para revisión en %(episode_segment)sel proyecto %(project_name)s.</p>
""",
        "playlist_episode_segment": "el episodio %(episode_name)s de ",
        "playlist_elements_count": "\n<p>%(count)s elementos en la playlist.</p>\n",
        "email_signature": "\n<p>Saludos cordiales,</p>\n\n<p>El equipo de %(organisation_name)s</p>",
    },
    "ja_JP": {
        # Comment notification
        "comment_subject": "[Kitsu] %(task_status_name)s - %(author_first_name)s が %(task_name)s にコメントしました",
        "comment_title": "新しいコメント",
        "comment_body_with_text": """<p><strong>%(author_full_name)s</strong> が <a href="%(task_url)s">%(task_name)s</a> にコメントし、ステータスを <strong>%(task_status_name)s</strong> に設定しました。</p>

<p><em>%(comment_text)s</em></p>
""",
        "comment_body_status_only": """<p><strong>%(author_full_name)s</strong> が <a href="%(task_url)s">%(task_name)s</a> のステータスを <strong>%(task_status_name)s</strong> に変更しました。</p>
""",
        # Mention notification
        "mention_subject": "[Kitsu] %(author_first_name)s が %(task_name)s であなたをメンションしました",
        "mention_title": "新しいメンション",
        "mention_body": """<p><strong>%(author_full_name)s</strong> が <a href="%(task_url)s">%(task_name)s</a> のコメントであなたをメンションしました：</p>

<p><em>%(comment_text)s</em></p>
""",
        # Assignation notification
        "assignation_subject": "[Kitsu] %(task_name)s にアサインされました",
        "assignation_title": "新しいアサイン",
        "assignation_body": """<p><strong>%(author_full_name)s</strong> があなたを <a href="%(task_url)s">%(task_name)s</a> にアサインしました。</p>
""",
        # Reply notification
        "reply_subject": "[Kitsu] %(author_first_name)s が %(task_name)s に返信しました",
        "reply_title": "新しい返信",
        "reply_body": """<p><strong>%(author_full_name)s</strong> が <a href="%(task_url)s">%(task_name)s</a> に返信しました。</p>

<p><em>%(reply_text)s</em></p>
""",
        # Playlist ready notification
        "playlist_subject": "[Kitsu] プロジェクト %(project_name)s のプレイリスト %(playlist_name)s がレビュー可能です",
        "playlist_title": "新しいプレイリストの準備ができました",
        "playlist_body": """<p><strong>%(author_full_name)s</strong> より、プレイリスト <a href="%(playlist_url)s">%(playlist_name)s</a> が %(episode_segment)sプロジェクト %(project_name)s でレビュー可能になったとのお知らせです。</p>
""",
        "playlist_episode_segment": "エピソード %(episode_name)s の ",
        "playlist_elements_count": "\n<p>プレイリストに %(count)s 件の要素が含まれています。</p>\n",
        "email_signature": "\n<p>よろしくお願いいたします。</p>\n\n<p>%(organisation_name)s チーム</p>",
    },
    "de_DE": {
        "comment_subject": "[Kitsu] %(task_status_name)s - %(author_first_name)s hat %(task_name)s kommentiert",
        "comment_title": "Neuer Kommentar",
        "comment_body_with_text": """<p><strong>%(author_full_name)s</strong> hat einen Kommentar zu <a href="%(task_url)s">%(task_name)s</a> geschrieben und den Status auf <strong>%(task_status_name)s</strong> gesetzt.</p>

<p><em>%(comment_text)s</em></p>
""",
        "comment_body_status_only": """<p><strong>%(author_full_name)s</strong> hat den Status von <a href="%(task_url)s">%(task_name)s</a> auf <strong>%(task_status_name)s</strong> geändert.</p>
""",
        "mention_subject": "[Kitsu] %(author_first_name)s hat Sie in %(task_name)s erwähnt",
        "mention_title": "Neue Erwähnung",
        "mention_body": """<p><strong>%(author_full_name)s</strong> hat Sie in einem Kommentar zu <a href="%(task_url)s">%(task_name)s</a> erwähnt:</p>

<p><em>%(comment_text)s</em></p>
""",
        "assignation_subject": "[Kitsu] Sie wurden %(task_name)s zugewiesen",
        "assignation_title": "Neue Zuweisung",
        "assignation_body": """<p><strong>%(author_full_name)s</strong> hat Sie <a href="%(task_url)s">%(task_name)s</a> zugewiesen.</p>
""",
        "reply_subject": "[Kitsu] %(author_first_name)s hat auf %(task_name)s geantwortet",
        "reply_title": "Neue Antwort",
        "reply_body": """<p><strong>%(author_full_name)s</strong> hat auf <a href="%(task_url)s">%(task_name)s</a> geantwortet.</p>

<p><em>%(reply_text)s</em></p>
""",
        "playlist_subject": "[Kitsu] Die Playlist %(playlist_name)s im Projekt %(project_name)s ist zur Überprüfung bereit",
        "playlist_title": "Neue Playlist bereit",
        "playlist_body": """<p><strong>%(author_full_name)s</strong> teilt mit, dass die Playlist <a href="%(playlist_url)s">%(playlist_name)s</a> zur Überprüfung in %(episode_segment)sdem Projekt %(project_name)s bereit ist.</p>
""",
        "playlist_episode_segment": "der Episode %(episode_name)s von ",
        "playlist_elements_count": "\n<p>%(count)s Elemente sind in der Playlist enthalten.</p>\n",
        "email_signature": "\n<p>Mit freundlichen Grüßen,</p>\n\n<p>%(organisation_name)s Team</p>",
    },
    "nl_NL": {
        "comment_subject": "[Kitsu] %(task_status_name)s - %(author_first_name)s heeft gereageerd op %(task_name)s",
        "comment_title": "Nieuwe reactie",
        "comment_body_with_text": """<p><strong>%(author_full_name)s</strong> heeft een reactie geplaatst op <a href="%(task_url)s">%(task_name)s</a> en de status gezet op <strong>%(task_status_name)s</strong>.</p>

<p><em>%(comment_text)s</em></p>
""",
        "comment_body_status_only": """<p><strong>%(author_full_name)s</strong> heeft de status van <a href="%(task_url)s">%(task_name)s</a> gewijzigd naar <strong>%(task_status_name)s</strong>.</p>
""",
        "mention_subject": "[Kitsu] %(author_first_name)s heeft je vermeld in %(task_name)s",
        "mention_title": "Nieuwe vermelding",
        "mention_body": """<p><strong>%(author_full_name)s</strong> heeft je vermeld in een reactie op <a href="%(task_url)s">%(task_name)s</a>:</p>

<p><em>%(comment_text)s</em></p>
""",
        "assignation_subject": "[Kitsu] Je bent toegewezen aan %(task_name)s",
        "assignation_title": "Nieuwe toewijzing",
        "assignation_body": """<p><strong>%(author_full_name)s</strong> heeft je toegewezen aan <a href="%(task_url)s">%(task_name)s</a>.</p>
""",
        "reply_subject": "[Kitsu] %(author_first_name)s heeft geantwoord op %(task_name)s",
        "reply_title": "Nieuw antwoord",
        "reply_body": """<p><strong>%(author_full_name)s</strong> heeft geantwoord op <a href="%(task_url)s">%(task_name)s</a>.</p>

<p><em>%(reply_text)s</em></p>
""",
        "playlist_subject": "[Kitsu] De playlist %(playlist_name)s in project %(project_name)s is klaar voor beoordeling",
        "playlist_title": "Nieuwe playlist klaar",
        "playlist_body": """<p><strong>%(author_full_name)s</strong> meldt dat de playlist <a href="%(playlist_url)s">%(playlist_name)s</a> klaar is voor beoordeling binnen %(episode_segment)shet project %(project_name)s.</p>
""",
        "playlist_episode_segment": "de aflevering %(episode_name)s van ",
        "playlist_elements_count": "\n<p>%(count)s elementen staan in de playlist.</p>\n",
        "email_signature": "\n<p>Met vriendelijke groet,</p>\n\n<p>%(organisation_name)s Team</p>",
    },
    "zh_CN": {
        "comment_subject": "[Kitsu] %(task_status_name)s - %(author_first_name)s 在 %(task_name)s 上发表了评论",
        "comment_title": "新评论",
        "comment_body_with_text": """<p><strong>%(author_full_name)s</strong> 在 <a href="%(task_url)s">%(task_name)s</a> 上发表了评论，并将状态设为 <strong>%(task_status_name)s</strong>。</p>

<p><em>%(comment_text)s</em></p>
""",
        "comment_body_status_only": """<p><strong>%(author_full_name)s</strong> 将 <a href="%(task_url)s">%(task_name)s</a> 的状态改为 <strong>%(task_status_name)s</strong>。</p>
""",
        "mention_subject": "[Kitsu] %(author_first_name)s 在 %(task_name)s 中提到了您",
        "mention_title": "新@提及",
        "mention_body": """<p><strong>%(author_full_name)s</strong> 在 <a href="%(task_url)s">%(task_name)s</a> 的评论中提到了您：</p>

<p><em>%(comment_text)s</em></p>
""",
        "assignation_subject": "[Kitsu] 您已被分配至 %(task_name)s",
        "assignation_title": "新分配",
        "assignation_body": """<p><strong>%(author_full_name)s</strong> 已将您分配至 <a href="%(task_url)s">%(task_name)s</a>。</p>
""",
        "reply_subject": "[Kitsu] %(author_first_name)s 在 %(task_name)s 上回复了",
        "reply_title": "新回复",
        "reply_body": """<p><strong>%(author_full_name)s</strong> 在 <a href="%(task_url)s">%(task_name)s</a> 上回复了。</p>

<p><em>%(reply_text)s</em></p>
""",
        "playlist_subject": "[Kitsu] 项目 %(project_name)s 中的播放列表 %(playlist_name)s 已可审核",
        "playlist_title": "新播放列表已就绪",
        "playlist_body": """<p><strong>%(author_full_name)s</strong> 通知您，播放列表 <a href="%(playlist_url)s">%(playlist_name)s</a> 已在 %(episode_segment)s项目 %(project_name)s 中准备好供审核。</p>
""",
        "playlist_episode_segment": "第 %(episode_name)s 集 ",
        "playlist_elements_count": "\n<p>播放列表中共 %(count)s 个元素。</p>\n",
        "email_signature": "\n<p>此致</p>\n\n<p>%(organisation_name)s 团队</p>",
    },
    "pt_BR": {
        "comment_subject": "[Kitsu] %(task_status_name)s - %(author_first_name)s comentou em %(task_name)s",
        "comment_title": "Novo comentário",
        "comment_body_with_text": """<p><strong>%(author_full_name)s</strong> escreveu um comentário em <a href="%(task_url)s">%(task_name)s</a> e definiu o status como <strong>%(task_status_name)s</strong>.</p>

<p><em>%(comment_text)s</em></p>
""",
        "comment_body_status_only": """<p><strong>%(author_full_name)s</strong> alterou o status de <a href="%(task_url)s">%(task_name)s</a> para <strong>%(task_status_name)s</strong>.</p>
""",
        "mention_subject": "[Kitsu] %(author_first_name)s mencionou você em %(task_name)s",
        "mention_title": "Nova menção",
        "mention_body": """<p><strong>%(author_full_name)s</strong> mencionou você em um comentário em <a href="%(task_url)s">%(task_name)s</a>:</p>

<p><em>%(comment_text)s</em></p>
""",
        "assignation_subject": "[Kitsu] Você foi atribuído a %(task_name)s",
        "assignation_title": "Nova atribuição",
        "assignation_body": """<p><strong>%(author_full_name)s</strong> atribuiu você a <a href="%(task_url)s">%(task_name)s</a>.</p>
""",
        "reply_subject": "[Kitsu] %(author_first_name)s respondeu em %(task_name)s",
        "reply_title": "Nova resposta",
        "reply_body": """<p><strong>%(author_full_name)s</strong> respondeu em <a href="%(task_url)s">%(task_name)s</a>.</p>

<p><em>%(reply_text)s</em></p>
""",
        "playlist_subject": "[Kitsu] A playlist %(playlist_name)s no projeto %(project_name)s está pronta para revisão",
        "playlist_title": "Nova playlist pronta",
        "playlist_body": """<p><strong>%(author_full_name)s</strong> informa que a playlist <a href="%(playlist_url)s">%(playlist_name)s</a> está pronta para revisão em %(episode_segment)so projeto %(project_name)s.</p>
""",
        "playlist_episode_segment": "o episódio %(episode_name)s de ",
        "playlist_elements_count": "\n<p>%(count)s elementos na playlist.</p>\n",
        "email_signature": "\n<p>Atenciosamente,</p>\n\n<p>Equipe %(organisation_name)s</p>",
    },
}


def _normalize_locale(locale):
    """
    Return a locale string suitable for lookup (e.g. en_US, fr_FR).
    """
    if not locale or not isinstance(locale, str):
        locale = "en_US"

    locale = locale.strip()
    if len(locale) == 2:
        lang_map = {
            "en": "en_US",
            "fr": "fr_FR",
            "es": "es_ES",
            "ja": "ja_JP",
            "de": "de_DE",
            "nl": "nl_NL",
            "zh": "zh_CN",
            "pt": "pt_BR",
        }
        return lang_map.get(locale.lower(), locale)
    return locale


def get_email_translation(locale, key, **params):
    """
    Return the translated string for the given locale and key.
    Interpolates params with %(name)s placeholders.

    Fallback order if the locale is missing or not supported:
    1. User's locale (e.g. fr_FR, ja_JP)
    2. en_US (default English)
    3. config.DEFAULT_LOCALE (usually en_US)
    """
    normalized = _normalize_locale(locale)
    fallback_chain = (
        normalized,
        "en_US",  # Always fall back to US English if locale unsupported
        getattr(config, "DEFAULT_LOCALE", "en_US"),
    )
    for candidate in fallback_chain:
        if not candidate:
            continue
        trans = EMAIL_TRANSLATIONS.get(candidate)
        if trans and key in trans:
            try:
                return trans[key] % params
            except (KeyError, TypeError):
                return trans[key]
    # Last resort: use key as string (should not happen if en_US is complete)
    return key
