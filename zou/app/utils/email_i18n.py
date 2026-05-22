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
# Use {name} placeholders for interpolation.
EMAIL_TRANSLATIONS = {
    "en_US": {
        # Comment notification
        "comment_subject": "[Kitsu] {task_status_name} - {author_first_name} commented on {task_name}",
        "comment_title": "New Comment",
        "comment_body_with_text": """<p><strong>{author_full_name}</strong> wrote a comment on <a href="{task_url}">{task_name}</a> and set the status to <strong>{task_status_name}</strong>.</p>

<p><em>{comment_text}</em></p>
""",
        "comment_body_status_only": """<p><strong>{author_full_name}</strong> changed status of <a href="{task_url}">{task_name}</a> to <strong>{task_status_name}</strong>.</p>
""",
        # Mention notification
        "mention_subject": "[Kitsu] {author_first_name} mentioned you on {task_name}",
        "mention_title": "New Mention",
        "mention_body": """<p><strong>{author_full_name}</strong> mentioned you in a comment on <a href="{task_url}">{task_name}</a>:</p>

<p><em>{comment_text}</em></p>
""",
        # Assignation notification
        "assignation_subject": "[Kitsu] You were assigned to {task_name}",
        "assignation_title": "New Assignation",
        "assignation_body": """<p><strong>{author_full_name}</strong> assigned you to <a href="{task_url}">{task_name}</a>.</p>
""",
        # Reply notification
        "reply_subject": "[Kitsu] {author_first_name} replied on {task_name}",
        "reply_title": "New Reply",
        "reply_body": """<p><strong>{author_full_name}</strong> wrote a reply on <a href="{task_url}">{task_name}</a>.</p>

<p><em>{reply_text}</em></p>
""",
        # Playlist ready notification
        "playlist_subject": "[Kitsu] The playlist {playlist_name} in project {project_name} is ready for review",
        "playlist_title": "New Playlist Ready",
        "playlist_body": """<p><strong>{author_full_name}</strong> notifies you that playlist <a href="{playlist_url}">{playlist_name}</a> is ready for a review under {episode_segment}the project {project_name}.</p>
""",
        "playlist_episode_segment": "the episode {episode_name} of ",
        "playlist_elements_count": "\n<p>{count} elements are listed in the playlist.</p>\n",
        # Shared playlist invitation
        "share_invitation_subject": "[Kitsu] {author_full_name} invited you to review {playlist_name}",
        "share_invitation_title": "Review invitation",
        "share_invitation_body": """<p><strong>{author_full_name}</strong> invited you to review the playlist <strong>{playlist_name}</strong> in project <strong>{project_name}</strong>.</p>

<p>You can open the review session here: <a href="{share_url}">{share_url}</a></p>
""",
        "share_invitation_message_segment": "\n<p><em>{message}</em></p>\n",
        "email_signature": "\n<p>Best regards,</p>\n\n<p>{organisation_name} Team</p>",
        # Auth: Email OTP
        "auth_otp_subject": "{organisation_name} - Kitsu: your verification code",
        "auth_otp_title": "Your verification code",
        "auth_otp_body": """<p>Hello {first_name},</p>

<p>Your verification code is: <strong>{otp}</strong></p>

<p>This one time password will expire after 5 minutes. After, you will have to request a new one.
This email was sent at this date: {time_string}.
The IP of the person who requested this is: {person_IP}.</p>
""",
        # Auth: Password changed
        "auth_password_changed_subject": "{organisation_name} - Kitsu: password changed",
        "auth_password_changed_title": "Password Changed",
        "auth_password_changed_body": """<p>Hello {first_name},</p>

<p>You have successfully changed your password at this date: {time_string}.</p>
<p>Your IP when you have changed your password is: {person_IP}.</p>
""",
        # Auth: Password recovery
        "auth_password_recovery_subject": "{organisation_name} - Kitsu: password recovery",
        "auth_password_recovery_title": "Password Recovery",
        "auth_password_recovery_body": """<p>Hello {first_name},</p>

<p>You have requested a password reset. Click on the following button to change your password:</p>

<p class="cta"><a class="button" href="{reset_url}">Change your password</a></p>

<p>This link will expire after 2 hours. After, you have to do a new request to reset your password.
This email was sent at this date: {time_string}.
The IP of the person who requested this is: {person_IP}.</p>
""",
        # Auth: Invitation
        "auth_invitation_subject": "You are invited by {organisation_name} to join their Kitsu platform",
        "auth_invitation_title": "Welcome to Kitsu",
        "auth_invitation_body": """<p>Hello {first_name},</p>
<p>You are invited by {organisation_name} to join their team on Kitsu.</p>
<p>Your login is: <strong>{email}</strong></p>
<p>Set your password to continue:</p>
<p class="cta"><a class="button" href="{reset_url}">Set your password</a></p>
""",
        # Auth: Password changed by admin
        "auth_password_changed_by_admin_subject": "{organisation_name} - Kitsu: password changed",
        "auth_password_changed_by_admin_title": "Password Changed",
        "auth_password_changed_by_admin_body": """<p>Hello {first_name},</p>
<p>Your password was changed at this date: {time_string}.</p>
<p>The IP of the user who changed your password is: {person_IP}.</p>
<p>If you don't know the person who changed the password, please contact our support team.</p>
""",
        # Auth: Two factor authentication disabled by admin
        "auth_2fa_disabled_by_admin_subject": "{organisation_name} - Kitsu: two factor authentication disabled",
        "auth_2fa_disabled_by_admin_title": "Two Factor Authentication Disabled",
        "auth_2fa_disabled_by_admin_body": """<p>Hello {first_name},</p>
<p>Your two factor authentication was disabled at this date: {time_string}.</p>
<p>The IP of the user who disabled your two factor authentication is: {person_IP}.</p>
<p>If you don't know the person who disabled the two factor authentication, please contact our support team.</p>
""",
    },
    "fr_FR": {
        # Comment notification
        "comment_subject": "[Kitsu] {task_status_name} - {author_first_name} a commenté {task_name}",
        "comment_title": "Nouveau commentaire",
        "comment_body_with_text": """<p><strong>{author_full_name}</strong> a écrit un commentaire sur <a href="{task_url}">{task_name}</a> et a défini le statut à <strong>{task_status_name}</strong>.</p>

<p><em>{comment_text}</em></p>
""",
        "comment_body_status_only": """<p><strong>{author_full_name}</strong> a changé le statut de <a href="{task_url}">{task_name}</a> en <strong>{task_status_name}</strong>.</p>
""",
        # Mention notification
        "mention_subject": "[Kitsu] {author_first_name} vous a mentionné sur {task_name}",
        "mention_title": "Nouvelle mention",
        "mention_body": """<p><strong>{author_full_name}</strong> vous a mentionné dans un commentaire sur <a href="{task_url}">{task_name}</a> :</p>

<p><em>{comment_text}</em></p>
""",
        # Assignation notification
        "assignation_subject": "[Kitsu] Vous avez été assigné à {task_name}",
        "assignation_title": "Nouvelle assignation",
        "assignation_body": """<p><strong>{author_full_name}</strong> vous a assigné à <a href="{task_url}">{task_name}</a>.</p>
""",
        # Reply notification
        "reply_subject": "[Kitsu] {author_first_name} a répondu sur {task_name}",
        "reply_title": "Nouvelle réponse",
        "reply_body": """<p><strong>{author_full_name}</strong> a répondu sur <a href="{task_url}">{task_name}</a>.</p>

<p><em>{reply_text}</em></p>
""",
        # Playlist ready notification
        "playlist_subject": "[Kitsu] La playlist {playlist_name} du projet {project_name} est prête pour relecture",
        "playlist_title": "Nouvelle playlist prête",
        "playlist_body": """<p><strong>{author_full_name}</strong> vous informe que la playlist <a href="{playlist_url}">{playlist_name}</a> est prête pour relecture dans {episode_segment}le projet {project_name}.</p>
""",
        "playlist_episode_segment": "l'épisode {episode_name} du ",
        "playlist_elements_count": "\n<p>{count} éléments sont dans la playlist.</p>\n",
        # Shared playlist invitation
        "share_invitation_subject": "[Kitsu] {author_full_name} vous invite à relire {playlist_name}",
        "share_invitation_title": "Invitation à une relecture",
        "share_invitation_body": """<p><strong>{author_full_name}</strong> vous invite à relire la playlist <strong>{playlist_name}</strong> dans le projet <strong>{project_name}</strong>.</p>

<p>Vous pouvez ouvrir la session de relecture ici : <a href="{share_url}">{share_url}</a></p>
""",
        "share_invitation_message_segment": "\n<p><em>{message}</em></p>\n",
        "email_signature": "\n<p>Cordialement,</p>\n\n<p>L'équipe {organisation_name}</p>",
        "auth_otp_subject": "{organisation_name} - Kitsu : votre code de vérification",
        "auth_otp_title": "Votre code de vérification",
        "auth_otp_body": """<p>Bonjour {first_name},</p>

<p>Votre code de vérification est : <strong>{otp}</strong></p>

<p>Ce mot de passe à usage unique expire dans 5 minutes. Ensuite, vous devrez en demander un nouveau.
Cet e-mail a été envoyé à la date : {time_string}.
L'IP de la personne ayant fait la demande est : {person_IP}.</p>
""",
        "auth_password_changed_subject": "{organisation_name} - Kitsu : mot de passe modifié",
        "auth_password_changed_title": "Mot de passe modifié",
        "auth_password_changed_body": """<p>Bonjour {first_name},</p>

<p>Vous avez modifié votre mot de passe avec succès à la date : {time_string}.</p>
<p>Votre adresse IP lors du changement est : {person_IP}.</p>
""",
        "auth_password_recovery_subject": "{organisation_name} - Kitsu : récupération de mot de passe",
        "auth_password_recovery_title": "Récupération de mot de passe",
        "auth_password_recovery_body": """<p>Bonjour {first_name},</p>

<p>Vous avez demandé une réinitialisation de mot de passe. Cliquez sur le bouton suivant pour le modifier :</p>

<p class="cta"><a class="button" href="{reset_url}">Changer votre mot de passe</a></p>

<p>Ce lien expire dans 2 heures. Ensuite, vous devrez faire une nouvelle demande.
Cet e-mail a été envoyé à la date : {time_string}.
L'IP de la personne ayant fait la demande est : {person_IP}.</p>
""",
        "auth_invitation_subject": "Vous êtes invité par {organisation_name} à rejoindre leur plateforme Kitsu",
        "auth_invitation_title": "Bienvenue sur Kitsu",
        "auth_invitation_body": """<p>Bonjour {first_name},</p>
<p>Vous êtes invité par {organisation_name} à rejoindre leur équipe sur Kitsu.</p>
<p>Votre identifiant : <strong>{email}</strong></p>
<p>Définissez votre mot de passe pour continuer :</p>
<p class="cta"><a class="button" href="{reset_url}">Définir votre mot de passe</a></p>
""",
        # Auth: Password changed by admin
        "auth_password_changed_by_admin_subject": "{organisation_name} - Kitsu : mot de passe modifié par un administrateur",
        "auth_password_changed_by_admin_title": "Mot de passe modifié",
        "auth_password_changed_by_admin_body": """<p>Bonjour {first_name},</p>
<p>Votre mot de passe a été modifié à cette date : {time_string}.</p>
<p>L'IP de la personne qui a modifié votre mot de passe est : {person_IP}.</p>
<p>Si vous ne connaissez pas cette personne, veuillez contacter notre équipe de support.</p>
""",
        # Auth: Two factor authentication disabled by admin
        "auth_2fa_disabled_by_admin_subject": "{organisation_name} - Kitsu : authentification à deux facteurs désactivée",
        "auth_2fa_disabled_by_admin_title": "Authentification à deux facteurs désactivée",
        "auth_2fa_disabled_by_admin_body": """<p>Bonjour {first_name},</p>
<p>Votre authentification à deux facteurs a été désactivée à cette date : {time_string}.</p>
<p>L'IP de la personne qui a désactivé votre authentification à deux facteurs est : {person_IP}.</p>
<p>Si vous ne connaissez pas cette personne, veuillez contacter notre équipe de support.</p>
""",
    },
    "es_ES": {
        # Comment notification
        "comment_subject": "[Kitsu] {task_status_name} - {author_first_name} comentó en {task_name}",
        "comment_title": "Nuevo comentario",
        "comment_body_with_text": """<p><strong>{author_full_name}</strong> escribió un comentario en <a href="{task_url}">{task_name}</a> y estableció el estado en <strong>{task_status_name}</strong>.</p>

<p><em>{comment_text}</em></p>
""",
        "comment_body_status_only": """<p><strong>{author_full_name}</strong> cambió el estado de <a href="{task_url}">{task_name}</a> a <strong>{task_status_name}</strong>.</p>
""",
        # Mention notification
        "mention_subject": "[Kitsu] {author_first_name} te mencionó en {task_name}",
        "mention_title": "Nueva mención",
        "mention_body": """<p><strong>{author_full_name}</strong> te mencionó en un comentario en <a href="{task_url}">{task_name}</a>:</p>

<p><em>{comment_text}</em></p>
""",
        # Assignation notification
        "assignation_subject": "[Kitsu] Has sido asignado a {task_name}",
        "assignation_title": "Nueva asignación",
        "assignation_body": """<p><strong>{author_full_name}</strong> te asignó a <a href="{task_url}">{task_name}</a>.</p>
""",
        # Reply notification
        "reply_subject": "[Kitsu] {author_first_name} respondió en {task_name}",
        "reply_title": "Nueva respuesta",
        "reply_body": """<p><strong>{author_full_name}</strong> respondió en <a href="{task_url}">{task_name}</a>.</p>

<p><em>{reply_text}</em></p>
""",
        # Playlist ready notification
        "playlist_subject": "[Kitsu] La playlist {playlist_name} del proyecto {project_name} está lista para revisión",
        "playlist_title": "Nueva playlist lista",
        "playlist_body": """<p><strong>{author_full_name}</strong> te informa que la playlist <a href="{playlist_url}">{playlist_name}</a> está lista para revisión en {episode_segment}el proyecto {project_name}.</p>
""",
        "playlist_episode_segment": "el episodio {episode_name} de ",
        "playlist_elements_count": "\n<p>{count} elementos en la playlist.</p>\n",
        # Shared playlist invitation
        "share_invitation_subject": "[Kitsu] {author_full_name} te invita a revisar {playlist_name}",
        "share_invitation_title": "Invitación a una revisión",
        "share_invitation_body": """<p><strong>{author_full_name}</strong> te invita a revisar la playlist <strong>{playlist_name}</strong> en el proyecto <strong>{project_name}</strong>.</p>

<p>Puedes abrir la sesión de revisión aquí: <a href="{share_url}">{share_url}</a></p>
""",
        "share_invitation_message_segment": "\n<p><em>{message}</em></p>\n",
        "email_signature": "\n<p>Saludos cordiales,</p>\n\n<p>El equipo de {organisation_name}</p>",
        "auth_otp_subject": "{organisation_name} - Kitsu: tu código de verificación",
        "auth_otp_title": "Tu código de verificación",
        "auth_otp_body": """<p>Hola {first_name},</p>

<p>Tu código de verificación es: <strong>{otp}</strong></p>

<p>Esta contraseña de un solo uso caduca en 5 minutos. Después tendrás que solicitar una nueva.
Este correo se envió en esta fecha: {time_string}.
La IP de la persona que lo solicitó es: {person_IP}.</p>
""",
        "auth_password_changed_subject": "{organisation_name} - Kitsu: contraseña cambiada",
        "auth_password_changed_title": "Contraseña cambiada",
        "auth_password_changed_body": """<p>Hola {first_name},</p>

<p>Has cambiado tu contraseña correctamente en esta fecha: {time_string}.</p>
<p>Tu IP al cambiar la contraseña es: {person_IP}.</p>
""",
        "auth_password_recovery_subject": "{organisation_name} - Kitsu: recuperación de contraseña",
        "auth_password_recovery_title": "Recuperación de contraseña",
        "auth_password_recovery_body": """<p>Hola {first_name},</p>

<p>Has solicitado restablecer tu contraseña. Haz clic en el siguiente botón para cambiarla:</p>

<p class="cta"><a class="button" href="{reset_url}">Cambiar tu contraseña</a></p>

<p>Este enlace caduca en 2 horas. Después tendrás que solicitar un nuevo restablecimiento.
Este correo se envió en esta fecha: {time_string}.
La IP de la persona que lo solicitó es: {person_IP}.</p>
""",
        "auth_invitation_subject": "Has sido invitado por {organisation_name} a unirte a su plataforma Kitsu",
        "auth_invitation_title": "Bienvenido a Kitsu",
        "auth_invitation_body": """<p>Hola {first_name},</p>
<p>Has sido invitado por {organisation_name} a unirte a su equipo en Kitsu.</p>
<p>Tu inicio de sesión es: <strong>{email}</strong></p>
<p>Establece tu contraseña para continuar:</p>
<p class="cta"><a class="button" href="{reset_url}">Establecer tu contraseña</a></p>
""",
        # Auth: Password changed by admin
        "auth_password_changed_by_admin_subject": "{organisation_name} - Kitsu: contraseña cambiada por un administrador",
        "auth_password_changed_by_admin_title": "Contraseña cambiada",
        "auth_password_changed_by_admin_body": """<p>Hola {first_name},</p>
<p>Tu contraseña fue cambiada en esta fecha: {time_string}.</p>
<p>La IP de la persona que cambió tu contraseña es: {person_IP}.</p>
<p>Si no conoces a esta persona, por favor contacta a nuestro equipo de soporte.</p>
""",
        # Auth: Two factor authentication disabled by admin
        "auth_2fa_disabled_by_admin_subject": "{organisation_name} - Kitsu: autenticación de dos factores desactivada",
        "auth_2fa_disabled_by_admin_title": "Autenticación de dos factores desactivada",
        "auth_2fa_disabled_by_admin_body": """<p>Hola {first_name},</p>
<p>Tu autenticación de dos factores fue desactivada en esta fecha: {time_string}.</p>
<p>La IP de la persona que desactivó tu autenticación de dos factores es: {person_IP}.</p>
<p>Si no conoces a esta persona, por favor contacta a nuestro equipo de soporte.</p>
""",
    },
    "ja_JP": {
        # Comment notification
        "comment_subject": "[Kitsu] {task_status_name} - {author_first_name} が {task_name} にコメントしました",
        "comment_title": "新しいコメント",
        "comment_body_with_text": """<p><strong>{author_full_name}</strong> が <a href="{task_url}">{task_name}</a> にコメントし、ステータスを <strong>{task_status_name}</strong> に設定しました。</p>

<p><em>{comment_text}</em></p>
""",
        "comment_body_status_only": """<p><strong>{author_full_name}</strong> が <a href="{task_url}">{task_name}</a> のステータスを <strong>{task_status_name}</strong> に変更しました。</p>
""",
        # Mention notification
        "mention_subject": "[Kitsu] {author_first_name} が {task_name} であなたをメンションしました",
        "mention_title": "新しいメンション",
        "mention_body": """<p><strong>{author_full_name}</strong> が <a href="{task_url}">{task_name}</a> のコメントであなたをメンションしました：</p>

<p><em>{comment_text}</em></p>
""",
        # Assignation notification
        "assignation_subject": "[Kitsu] {task_name} にアサインされました",
        "assignation_title": "新しいアサイン",
        "assignation_body": """<p><strong>{author_full_name}</strong> があなたを <a href="{task_url}">{task_name}</a> にアサインしました。</p>
""",
        # Reply notification
        "reply_subject": "[Kitsu] {author_first_name} が {task_name} に返信しました",
        "reply_title": "新しい返信",
        "reply_body": """<p><strong>{author_full_name}</strong> が <a href="{task_url}">{task_name}</a> に返信しました。</p>

<p><em>{reply_text}</em></p>
""",
        # Playlist ready notification
        "playlist_subject": "[Kitsu] プロジェクト {project_name} のプレイリスト {playlist_name} がレビュー可能です",
        "playlist_title": "新しいプレイリストの準備ができました",
        "playlist_body": """<p><strong>{author_full_name}</strong> より、プレイリスト <a href="{playlist_url}">{playlist_name}</a> が {episode_segment}プロジェクト {project_name} でレビュー可能になったとのお知らせです。</p>
""",
        "playlist_episode_segment": "エピソード {episode_name} の ",
        "playlist_elements_count": "\n<p>プレイリストに {count} 件の要素が含まれています。</p>\n",
        # Shared playlist invitation
        "share_invitation_subject": "[Kitsu] {author_full_name} さんが {playlist_name} のレビューに招待しました",
        "share_invitation_title": "レビューへの招待",
        "share_invitation_body": """<p><strong>{author_full_name}</strong> さんがプロジェクト <strong>{project_name}</strong> のプレイリスト <strong>{playlist_name}</strong> のレビューに招待しました。</p>

<p>レビューセッションはこちらから開けます: <a href="{share_url}">{share_url}</a></p>
""",
        "share_invitation_message_segment": "\n<p><em>{message}</em></p>\n",
        "email_signature": "\n<p>よろしくお願いいたします。</p>\n\n<p>{organisation_name} チーム</p>",
        "auth_otp_subject": "{organisation_name} - Kitsu: 認証コード",
        "auth_otp_title": "認証コード",
        "auth_otp_body": """<p>{first_name} 様</p>

<p>認証コードは <strong>{otp}</strong> です。</p>

<p>このワンタイムパスワードは5分で失効します。その後は新しいコードをリクエストしてください。
送信日時: {time_string}。
リクエスト元のIP: {person_IP}。</p>
""",
        "auth_password_changed_subject": "{organisation_name} - Kitsu: パスワードを変更しました",
        "auth_password_changed_title": "パスワード変更完了",
        "auth_password_changed_body": """<p>{first_name} 様</p>

<p>パスワードを正常に変更しました。変更日時: {time_string}。</p>
<p>変更時のIP: {person_IP}。</p>
""",
        "auth_password_recovery_subject": "{organisation_name} - Kitsu: パスワードのリセット",
        "auth_password_recovery_title": "パスワードのリセット",
        "auth_password_recovery_body": """<p>{first_name} 様</p>

<p>パスワードのリセットをリクエストされました。以下のボタンからパスワードを変更してください。</p>

<p class="cta"><a class="button" href="{reset_url}">パスワードを変更</a></p>

<p>このリンクは2時間で失効します。その後は再度リセットをリクエストしてください。
送信日時: {time_string}。
リクエスト元のIP: {person_IP}。</p>
""",
        "auth_invitation_subject": "{organisation_name} から Kitsu への招待",
        "auth_invitation_title": "Kitsu へようこそ",
        "auth_invitation_body": """<p>{first_name} 様</p>
<p>{organisation_name} より Kitsu のチームに参加する招待が届きました。</p>
<p>ログイン: <strong>{email}</strong></p>
<p>続行するにはパスワードを設定してください:</p>
<p class="cta"><a class="button" href="{reset_url}">パスワードを設定</a></p>
""",
        # Auth: Password changed by admin
        "auth_password_changed_by_admin_subject": "{organisation_name} - Kitsu: 管理者によりパスワードが変更されました",
        "auth_password_changed_by_admin_title": "パスワード変更完了",
        "auth_password_changed_by_admin_body": """<p>{first_name} 様</p>
<p>あなたのパスワードが次の日時に変更されました: {time_string}。</p>
<p>パスワードを変更した人のIPアドレス: {person_IP}。</p>
<p>心当たりがない場合は、サポートチームにご連絡ください。</p>
""",
        # Auth: Two factor authentication disabled by admin
        "auth_2fa_disabled_by_admin_subject": "{organisation_name} - Kitsu: 管理者により二要素認証が無効化されました",
        "auth_2fa_disabled_by_admin_title": "二要素認証が無効化されました",
        "auth_2fa_disabled_by_admin_body": """<p>{first_name} 様</p>
<p>あなたの二要素認証が次の日時に無効化されました: {time_string}。</p>
<p>二要素認証を無効化した人のIPアドレス: {person_IP}。</p>
<p>心当たりがない場合は、サポートチームにご連絡ください。</p>
""",
    },
    "de_DE": {
        "comment_subject": "[Kitsu] {task_status_name} - {author_first_name} hat {task_name} kommentiert",
        "comment_title": "Neuer Kommentar",
        "comment_body_with_text": """<p><strong>{author_full_name}</strong> hat einen Kommentar zu <a href="{task_url}">{task_name}</a> geschrieben und den Status auf <strong>{task_status_name}</strong> gesetzt.</p>

<p><em>{comment_text}</em></p>
""",
        "comment_body_status_only": """<p><strong>{author_full_name}</strong> hat den Status von <a href="{task_url}">{task_name}</a> auf <strong>{task_status_name}</strong> geändert.</p>
""",
        "mention_subject": "[Kitsu] {author_first_name} hat Sie in {task_name} erwähnt",
        "mention_title": "Neue Erwähnung",
        "mention_body": """<p><strong>{author_full_name}</strong> hat Sie in einem Kommentar zu <a href="{task_url}">{task_name}</a> erwähnt:</p>

<p><em>{comment_text}</em></p>
""",
        "assignation_subject": "[Kitsu] Sie wurden {task_name} zugewiesen",
        "assignation_title": "Neue Zuweisung",
        "assignation_body": """<p><strong>{author_full_name}</strong> hat Sie <a href="{task_url}">{task_name}</a> zugewiesen.</p>
""",
        "reply_subject": "[Kitsu] {author_first_name} hat auf {task_name} geantwortet",
        "reply_title": "Neue Antwort",
        "reply_body": """<p><strong>{author_full_name}</strong> hat auf <a href="{task_url}">{task_name}</a> geantwortet.</p>

<p><em>{reply_text}</em></p>
""",
        "playlist_subject": "[Kitsu] Die Playlist {playlist_name} im Projekt {project_name} ist zur Überprüfung bereit",
        "playlist_title": "Neue Playlist bereit",
        "playlist_body": """<p><strong>{author_full_name}</strong> teilt mit, dass die Playlist <a href="{playlist_url}">{playlist_name}</a> zur Überprüfung in {episode_segment}dem Projekt {project_name} bereit ist.</p>
""",
        "playlist_episode_segment": "der Episode {episode_name} von ",
        "playlist_elements_count": "\n<p>{count} Elemente sind in der Playlist enthalten.</p>\n",
        # Shared playlist invitation
        "share_invitation_subject": "[Kitsu] {author_full_name} lädt dich ein, {playlist_name} zu prüfen",
        "share_invitation_title": "Einladung zur Begutachtung",
        "share_invitation_body": """<p><strong>{author_full_name}</strong> lädt dich ein, die Playlist <strong>{playlist_name}</strong> im Projekt <strong>{project_name}</strong> zu prüfen.</p>

<p>Du kannst die Begutachtung hier öffnen: <a href="{share_url}">{share_url}</a></p>
""",
        "share_invitation_message_segment": "\n<p><em>{message}</em></p>\n",
        "email_signature": "\n<p>Mit freundlichen Grüßen,</p>\n\n<p>{organisation_name} Team</p>",
        "auth_otp_subject": "{organisation_name} - Kitsu: Ihr Bestätigungscode",
        "auth_otp_title": "Ihr Bestätigungscode",
        "auth_otp_body": """<p>Hallo {first_name},</p>

<p>Ihr Bestätigungscode lautet: <strong>{otp}</strong></p>

<p>Dieses Einmalpasswort läuft nach 5 Minuten ab. Danach müssen Sie einen neuen anfordern.
Diese E-Mail wurde am {time_string} gesendet.
Die IP der anfragenden Person ist: {person_IP}.</p>
""",
        "auth_password_changed_subject": "{organisation_name} - Kitsu: Passwort geändert",
        "auth_password_changed_title": "Passwort geändert",
        "auth_password_changed_body": """<p>Hallo {first_name},</p>

<p>Sie haben Ihr Passwort erfolgreich am {time_string} geändert.</p>
<p>Ihre IP bei der Änderung war: {person_IP}.</p>
""",
        "auth_password_recovery_subject": "{organisation_name} - Kitsu: Passwort-Wiederherstellung",
        "auth_password_recovery_title": "Passwort-Wiederherstellung",
        "auth_password_recovery_body": """<p>Hallo {first_name},</p>

<p>Sie haben eine Passwort-Zurücksetzung angefordert. Klicken Sie auf die Schaltfläche unten, um Ihr Passwort zu ändern:</p>

<p class="cta"><a class="button" href="{reset_url}">Passwort ändern</a></p>

<p>Dieser Link läuft nach 2 Stunden ab. Danach müssen Sie eine neue Anfrage stellen.
Diese E-Mail wurde am {time_string} gesendet.
Die IP der anfragenden Person ist: {person_IP}.</p>
""",
        "auth_invitation_subject": "Sie wurden von {organisation_name} eingeladen, der Kitsu-Plattform beizutreten",
        "auth_invitation_title": "Willkommen bei Kitsu",
        "auth_invitation_body": """<p>Hallo {first_name},</p>
<p>Sie wurden von {organisation_name} eingeladen, ihrem Team auf Kitsu beizutreten.</p>
<p>Ihre Anmeldung: <strong>{email}</strong></p>
<p>Setzen Sie Ihr Passwort, um fortzufahren:</p>
<p class="cta"><a class="button" href="{reset_url}">Passwort setzen</a></p>
""",
        # Auth: Password changed by admin
        "auth_password_changed_by_admin_subject": "{organisation_name} - Kitsu: Passwort von einem Administrator geändert",
        "auth_password_changed_by_admin_title": "Passwort geändert",
        "auth_password_changed_by_admin_body": """<p>Hallo {first_name},</p>
<p>Ihr Passwort wurde zu diesem Zeitpunkt geändert: {time_string}.</p>
<p>Die IP der Person, die Ihr Passwort geändert hat, ist: {person_IP}.</p>
<p>Wenn Sie diese Person nicht kennen, kontaktieren Sie bitte unser Support-Team.</p>
""",
        # Auth: Two factor authentication disabled by admin
        "auth_2fa_disabled_by_admin_subject": "{organisation_name} - Kitsu: Zwei-Faktor-Authentifizierung deaktiviert",
        "auth_2fa_disabled_by_admin_title": "Zwei-Faktor-Authentifizierung deaktiviert",
        "auth_2fa_disabled_by_admin_body": """<p>Hallo {first_name},</p>
<p>Ihre Zwei-Faktor-Authentifizierung wurde zu diesem Zeitpunkt deaktiviert: {time_string}.</p>
<p>Die IP der Person, die Ihre Zwei-Faktor-Authentifizierung deaktiviert hat, ist: {person_IP}.</p>
<p>Wenn Sie diese Person nicht kennen, kontaktieren Sie bitte unser Support-Team.</p>
""",
    },
    "nl_NL": {
        "comment_subject": "[Kitsu] {task_status_name} - {author_first_name} heeft gereageerd op {task_name}",
        "comment_title": "Nieuwe reactie",
        "comment_body_with_text": """<p><strong>{author_full_name}</strong> heeft een reactie geplaatst op <a href="{task_url}">{task_name}</a> en de status gezet op <strong>{task_status_name}</strong>.</p>

<p><em>{comment_text}</em></p>
""",
        "comment_body_status_only": """<p><strong>{author_full_name}</strong> heeft de status van <a href="{task_url}">{task_name}</a> gewijzigd naar <strong>{task_status_name}</strong>.</p>
""",
        "mention_subject": "[Kitsu] {author_first_name} heeft je vermeld in {task_name}",
        "mention_title": "Nieuwe vermelding",
        "mention_body": """<p><strong>{author_full_name}</strong> heeft je vermeld in een reactie op <a href="{task_url}">{task_name}</a>:</p>

<p><em>{comment_text}</em></p>
""",
        "assignation_subject": "[Kitsu] Je bent toegewezen aan {task_name}",
        "assignation_title": "Nieuwe toewijzing",
        "assignation_body": """<p><strong>{author_full_name}</strong> heeft je toegewezen aan <a href="{task_url}">{task_name}</a>.</p>
""",
        "reply_subject": "[Kitsu] {author_first_name} heeft geantwoord op {task_name}",
        "reply_title": "Nieuw antwoord",
        "reply_body": """<p><strong>{author_full_name}</strong> heeft geantwoord op <a href="{task_url}">{task_name}</a>.</p>

<p><em>{reply_text}</em></p>
""",
        "playlist_subject": "[Kitsu] De playlist {playlist_name} in project {project_name} is klaar voor beoordeling",
        "playlist_title": "Nieuwe playlist klaar",
        "playlist_body": """<p><strong>{author_full_name}</strong> meldt dat de playlist <a href="{playlist_url}">{playlist_name}</a> klaar is voor beoordeling binnen {episode_segment}het project {project_name}.</p>
""",
        "playlist_episode_segment": "de aflevering {episode_name} van ",
        "playlist_elements_count": "\n<p>{count} elementen staan in de playlist.</p>\n",
        # Shared playlist invitation
        "share_invitation_subject": "[Kitsu] {author_full_name} nodigt je uit om {playlist_name} te beoordelen",
        "share_invitation_title": "Uitnodiging voor beoordeling",
        "share_invitation_body": """<p><strong>{author_full_name}</strong> nodigt je uit om de playlist <strong>{playlist_name}</strong> in project <strong>{project_name}</strong> te beoordelen.</p>

<p>Je kunt de beoordelingssessie hier openen: <a href="{share_url}">{share_url}</a></p>
""",
        "share_invitation_message_segment": "\n<p><em>{message}</em></p>\n",
        "email_signature": "\n<p>Met vriendelijke groet,</p>\n\n<p>{organisation_name} Team</p>",
        "auth_otp_subject": "{organisation_name} - Kitsu: uw verificatiecode",
        "auth_otp_title": "Uw verificatiecode",
        "auth_otp_body": """<p>Hallo {first_name},</p>

<p>Uw verificatiecode is: <strong>{otp}</strong></p>

<p>Dit eenmalige wachtwoord verloopt na 5 minuten. Daarna moet u een nieuwe aanvragen.
Deze e-mail is verzonden op: {time_string}.
Het IP-adres van de aanvrager is: {person_IP}.</p>
""",
        "auth_password_changed_subject": "{organisation_name} - Kitsu: wachtwoord gewijzigd",
        "auth_password_changed_title": "Wachtwoord gewijzigd",
        "auth_password_changed_body": """<p>Hallo {first_name},</p>

<p>U heeft uw wachtwoord succesvol gewijzigd op: {time_string}.</p>
<p>Uw IP-adres bij de wijziging was: {person_IP}.</p>
""",
        "auth_password_recovery_subject": "{organisation_name} - Kitsu: wachtwoordherstel",
        "auth_password_recovery_title": "Wachtwoordherstel",
        "auth_password_recovery_body": """<p>Hallo {first_name},</p>

<p>U heeft een wachtwoordreset aangevraagd. Klik op de onderstaande knop om uw wachtwoord te wijzigen:</p>

<p class="cta"><a class="button" href="{reset_url}">Wachtwoord wijzigen</a></p>

<p>Deze link verloopt na 2 uur. Daarna moet u een nieuwe aanvraag doen.
Deze e-mail is verzonden op: {time_string}.
Het IP-adres van de aanvrager is: {person_IP}.</p>
""",
        "auth_invitation_subject": "U bent door {organisation_name} uitgenodigd om deel te nemen aan hun Kitsu-platform",
        "auth_invitation_title": "Welkom bij Kitsu",
        "auth_invitation_body": """<p>Hallo {first_name},</p>
<p>U bent door {organisation_name} uitgenodigd om deel te nemen aan hun team op Kitsu.</p>
<p>Uw inloggegevens: <strong>{email}</strong></p>
<p>Stel uw wachtwoord in om door te gaan:</p>
<p class="cta"><a class="button" href="{reset_url}">Wachtwoord instellen</a></p>
""",
        # Auth: Password changed by admin
        "auth_password_changed_by_admin_subject": "{organisation_name} - Kitsu: wachtwoord gewijzigd door een beheerder",
        "auth_password_changed_by_admin_title": "Wachtwoord gewijzigd",
        "auth_password_changed_by_admin_body": """<p>Hallo {first_name},</p>
<p>Uw wachtwoord is gewijzigd op: {time_string}.</p>
<p>Het IP-adres van de persoon die uw wachtwoord heeft gewijzigd is: {person_IP}.</p>
<p>Als u deze persoon niet kent, neem dan contact op met ons supportteam.</p>
""",
        # Auth: Two factor authentication disabled by admin
        "auth_2fa_disabled_by_admin_subject": "{organisation_name} - Kitsu: tweefactorauthenticatie uitgeschakeld",
        "auth_2fa_disabled_by_admin_title": "Tweefactorauthenticatie uitgeschakeld",
        "auth_2fa_disabled_by_admin_body": """<p>Hallo {first_name},</p>
<p>Uw tweefactorauthenticatie is uitgeschakeld op: {time_string}.</p>
<p>Het IP-adres van de persoon die uw tweefactorauthenticatie heeft uitgeschakeld is: {person_IP}.</p>
<p>Als u deze persoon niet kent, neem dan contact op met ons supportteam.</p>
""",
    },
    "zh_CN": {
        "comment_subject": "[Kitsu] {task_status_name} - {author_first_name} 在 {task_name} 上发表了评论",
        "comment_title": "新评论",
        "comment_body_with_text": """<p><strong>{author_full_name}</strong> 在 <a href="{task_url}">{task_name}</a> 上发表了评论，并将状态设为 <strong>{task_status_name}</strong>。</p>

<p><em>{comment_text}</em></p>
""",
        "comment_body_status_only": """<p><strong>{author_full_name}</strong> 将 <a href="{task_url}">{task_name}</a> 的状态改为 <strong>{task_status_name}</strong>。</p>
""",
        "mention_subject": "[Kitsu] {author_first_name} 在 {task_name} 中提到了您",
        "mention_title": "新@提及",
        "mention_body": """<p><strong>{author_full_name}</strong> 在 <a href="{task_url}">{task_name}</a> 的评论中提到了您：</p>

<p><em>{comment_text}</em></p>
""",
        "assignation_subject": "[Kitsu] 您已被分配至 {task_name}",
        "assignation_title": "新分配",
        "assignation_body": """<p><strong>{author_full_name}</strong> 已将您分配至 <a href="{task_url}">{task_name}</a>。</p>
""",
        "reply_subject": "[Kitsu] {author_first_name} 在 {task_name} 上回复了",
        "reply_title": "新回复",
        "reply_body": """<p><strong>{author_full_name}</strong> 在 <a href="{task_url}">{task_name}</a> 上回复了。</p>

<p><em>{reply_text}</em></p>
""",
        "playlist_subject": "[Kitsu] 项目 {project_name} 中的播放列表 {playlist_name} 已可审核",
        "playlist_title": "新播放列表已就绪",
        "playlist_body": """<p><strong>{author_full_name}</strong> 通知您，播放列表 <a href="{playlist_url}">{playlist_name}</a> 已在 {episode_segment}项目 {project_name} 中准备好供审核。</p>
""",
        "playlist_episode_segment": "第 {episode_name} 集 ",
        "playlist_elements_count": "\n<p>播放列表中共 {count} 个元素。</p>\n",
        # Shared playlist invitation
        "share_invitation_subject": "[Kitsu] {author_full_name} 邀请您审阅 {playlist_name}",
        "share_invitation_title": "审阅邀请",
        "share_invitation_body": """<p><strong>{author_full_name}</strong> 邀请您审阅项目 <strong>{project_name}</strong> 中的播放列表 <strong>{playlist_name}</strong>。</p>

<p>您可以在此打开审阅会话: <a href="{share_url}">{share_url}</a></p>
""",
        "share_invitation_message_segment": "\n<p><em>{message}</em></p>\n",
        "email_signature": "\n<p>此致</p>\n\n<p>{organisation_name} 团队</p>",
        "auth_otp_subject": "{organisation_name} - Kitsu：您的验证码",
        "auth_otp_title": "您的验证码",
        "auth_otp_body": """<p>您好 {first_name}，</p>

<p>您的验证码是：<strong>{otp}</strong></p>

<p>此一次性密码将在 5 分钟后失效，之后您需要重新请求。
此邮件发送时间：{time_string}。
请求者 IP：{person_IP}。</p>
""",
        "auth_password_changed_subject": "{organisation_name} - Kitsu：密码已修改",
        "auth_password_changed_title": "密码已修改",
        "auth_password_changed_body": """<p>您好 {first_name}，</p>

<p>您已成功于 {time_string} 修改密码。</p>
<p>修改时的 IP：{person_IP}。</p>
""",
        "auth_password_recovery_subject": "{organisation_name} - Kitsu：找回密码",
        "auth_password_recovery_title": "找回密码",
        "auth_password_recovery_body": """<p>您好 {first_name}，</p>

<p>您已请求重置密码。请点击下方按钮修改密码：</p>

<p class="cta"><a class="button" href="{reset_url}">修改密码</a></p>

<p>此链接将在 2 小时后失效，之后需重新请求。
此邮件发送时间：{time_string}。
请求者 IP：{person_IP}。</p>
""",
        "auth_invitation_subject": "{organisation_name} 邀请您加入 Kitsu 平台",
        "auth_invitation_title": "欢迎使用 Kitsu",
        "auth_invitation_body": """<p>您好 {first_name}，</p>
<p>{organisation_name} 邀请您加入他们在 Kitsu 的团队。</p>
<p>您的登录名：<strong>{email}</strong></p>
<p>请设置密码以继续：</p>
<p class="cta"><a class="button" href="{reset_url}">设置密码</a></p>
""",
        # Auth: Password changed by admin
        "auth_password_changed_by_admin_subject": "{organisation_name} - Kitsu：管理员已更改密码",
        "auth_password_changed_by_admin_title": "密码已更改",
        "auth_password_changed_by_admin_body": """<p>您好 {first_name}，</p>
<p>您的密码已于此日期更改：{time_string}。</p>
<p>更改您密码的人的 IP 地址为：{person_IP}。</p>
<p>如果您不认识此人，请联系我们的支持团队。</p>
""",
        # Auth: Two factor authentication disabled by admin
        "auth_2fa_disabled_by_admin_subject": "{organisation_name} - Kitsu：双因素认证已被管理员禁用",
        "auth_2fa_disabled_by_admin_title": "双因素认证已禁用",
        "auth_2fa_disabled_by_admin_body": """<p>您好 {first_name}，</p>
<p>您的双因素认证已于此日期被禁用：{time_string}。</p>
<p>禁用您双因素认证的人的 IP 地址为：{person_IP}。</p>
<p>如果您不认识此人，请联系我们的支持团队。</p>
""",
    },
    "pt_BR": {
        "comment_subject": "[Kitsu] {task_status_name} - {author_first_name} comentou em {task_name}",
        "comment_title": "Novo comentário",
        "comment_body_with_text": """<p><strong>{author_full_name}</strong> escreveu um comentário em <a href="{task_url}">{task_name}</a> e definiu o status como <strong>{task_status_name}</strong>.</p>

<p><em>{comment_text}</em></p>
""",
        "comment_body_status_only": """<p><strong>{author_full_name}</strong> alterou o status de <a href="{task_url}">{task_name}</a> para <strong>{task_status_name}</strong>.</p>
""",
        "mention_subject": "[Kitsu] {author_first_name} mencionou você em {task_name}",
        "mention_title": "Nova menção",
        "mention_body": """<p><strong>{author_full_name}</strong> mencionou você em um comentário em <a href="{task_url}">{task_name}</a>:</p>

<p><em>{comment_text}</em></p>
""",
        "assignation_subject": "[Kitsu] Você foi atribuído a {task_name}",
        "assignation_title": "Nova atribuição",
        "assignation_body": """<p><strong>{author_full_name}</strong> atribuiu você a <a href="{task_url}">{task_name}</a>.</p>
""",
        "reply_subject": "[Kitsu] {author_first_name} respondeu em {task_name}",
        "reply_title": "Nova resposta",
        "reply_body": """<p><strong>{author_full_name}</strong> respondeu em <a href="{task_url}">{task_name}</a>.</p>

<p><em>{reply_text}</em></p>
""",
        "playlist_subject": "[Kitsu] A playlist {playlist_name} no projeto {project_name} está pronta para revisão",
        "playlist_title": "Nova playlist pronta",
        "playlist_body": """<p><strong>{author_full_name}</strong> informa que a playlist <a href="{playlist_url}">{playlist_name}</a> está pronta para revisão em {episode_segment}o projeto {project_name}.</p>
""",
        "playlist_episode_segment": "o episódio {episode_name} de ",
        "playlist_elements_count": "\n<p>{count} elementos na playlist.</p>\n",
        # Shared playlist invitation
        "share_invitation_subject": "[Kitsu] {author_full_name} convidou você para revisar {playlist_name}",
        "share_invitation_title": "Convite para revisão",
        "share_invitation_body": """<p><strong>{author_full_name}</strong> convidou você para revisar a playlist <strong>{playlist_name}</strong> no projeto <strong>{project_name}</strong>.</p>

<p>Você pode abrir a sessão de revisão aqui: <a href="{share_url}">{share_url}</a></p>
""",
        "share_invitation_message_segment": "\n<p><em>{message}</em></p>\n",
        "email_signature": "\n<p>Atenciosamente,</p>\n\n<p>Equipe {organisation_name}</p>",
        "auth_otp_subject": "{organisation_name} - Kitsu: seu código de verificação",
        "auth_otp_title": "Seu código de verificação",
        "auth_otp_body": """<p>Olá {first_name},</p>

<p>Seu código de verificação é: <strong>{otp}</strong></p>

<p>Esta senha de uso único expira em 5 minutos. Depois, você precisará solicitar uma nova.
Este e-mail foi enviado em: {time_string}.
O IP de quem solicitou é: {person_IP}.</p>
""",
        "auth_password_changed_subject": "{organisation_name} - Kitsu: senha alterada",
        "auth_password_changed_title": "Senha alterada",
        "auth_password_changed_body": """<p>Olá {first_name},</p>

<p>Você alterou sua senha com sucesso em: {time_string}.</p>
<p>Seu IP ao alterar a senha foi: {person_IP}.</p>
""",
        "auth_password_recovery_subject": "{organisation_name} - Kitsu: recuperação de senha",
        "auth_password_recovery_title": "Recuperação de senha",
        "auth_password_recovery_body": """<p>Olá {first_name},</p>

<p>Você solicitou a redefinição de senha. Clique no botão abaixo para alterá-la:</p>

<p class="cta"><a class="button" href="{reset_url}">Alterar sua senha</a></p>

<p>Este link expira em 2 horas. Depois, você precisará fazer uma nova solicitação.
Este e-mail foi enviado em: {time_string}.
O IP de quem solicitou é: {person_IP}.</p>
""",
        "auth_invitation_subject": "Você foi convidado por {organisation_name} para participar da plataforma Kitsu",
        "auth_invitation_title": "Bem-vindo ao Kitsu",
        "auth_invitation_body": """<p>Olá {first_name},</p>
<p>Você foi convidado por {organisation_name} para participar da equipe no Kitsu.</p>
<p>Seu login: <strong>{email}</strong></p>
<p>Defina sua senha para continuar:</p>
<p class="cta"><a class="button" href="{reset_url}">Definir sua senha</a></p>
""",
        # Auth: Password changed by admin
        "auth_password_changed_by_admin_subject": "{organisation_name} - Kitsu: senha alterada por um administrador",
        "auth_password_changed_by_admin_title": "Senha alterada",
        "auth_password_changed_by_admin_body": """<p>Olá {first_name},</p>
<p>Sua senha foi alterada nesta data: {time_string}.</p>
<p>O IP da pessoa que alterou sua senha é: {person_IP}.</p>
<p>Se você não conhece esta pessoa, entre em contato com nossa equipe de suporte.</p>
""",
        # Auth: Two factor authentication disabled by admin
        "auth_2fa_disabled_by_admin_subject": "{organisation_name} - Kitsu: autenticação de dois fatores desativada",
        "auth_2fa_disabled_by_admin_title": "Autenticação de dois fatores desativada",
        "auth_2fa_disabled_by_admin_body": """<p>Olá {first_name},</p>
<p>Sua autenticação de dois fatores foi desativada nesta data: {time_string}.</p>
<p>O IP da pessoa que desativou sua autenticação de dois fatores é: {person_IP}.</p>
<p>Se você não conhece esta pessoa, entre em contato com nossa equipe de suporte.</p>
""",
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
    Interpolates params with {name} placeholders.

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
                return trans[key].format(**params)
            except (KeyError, TypeError):
                return trans[key]
    # Last resort: use key as string (should not happen if en_US is complete)
    return key
