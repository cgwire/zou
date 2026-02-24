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
        # Auth: Email OTP
        "auth_otp_subject": "%(organisation_name)s - Kitsu: your verification code",
        "auth_otp_title": "Your verification code",
        "auth_otp_body": """<p>Hello %(first_name)s,</p>

<p>Your verification code is: <strong>%(otp)s</strong></p>

<p>This one time password will expire after 5 minutes. After, you will have to request a new one.
This email was sent at this date: %(time_string)s.
The IP of the person who requested this is: %(person_IP)s.</p>
""",
        # Auth: Password changed
        "auth_password_changed_subject": "%(organisation_name)s - Kitsu: password changed",
        "auth_password_changed_title": "Password Changed",
        "auth_password_changed_body": """<p>Hello %(first_name)s,</p>

<p>You have successfully changed your password at this date: %(time_string)s.</p>
<p>Your IP when you have changed your password is: %(person_IP)s.</p>
""",
        # Auth: Password recovery
        "auth_password_recovery_subject": "%(organisation_name)s - Kitsu: password recovery",
        "auth_password_recovery_title": "Password Recovery",
        "auth_password_recovery_body": """<p>Hello %(first_name)s,</p>

<p>You have requested a password reset. Click on the following button to change your password:</p>

<p class="cta"><a class="button" href="%(reset_url)s">Change your password</a></p>

<p>This link will expire after 2 hours. After, you have to do a new request to reset your password.
This email was sent at this date: %(time_string)s.
The IP of the person who requested this is: %(person_IP)s.</p>
""",
        # Auth: Invitation
        "auth_invitation_subject": "You are invited by %(organisation_name)s to join their Kitsu platform",
        "auth_invitation_title": "Welcome to Kitsu",
        "auth_invitation_body": """<p>Hello %(first_name)s,</p>
<p>You are invited by %(organisation_name)s to join their team on Kitsu.</p>
<p>Your login is: <strong>%(email)s</strong></p>
<p>Set your password to continue:</p>
<p class="cta"><a class="button" href="%(reset_url)s">Set your password</a></p>
""",
        # Auth: Password changed by admin
        "auth_password_changed_by_admin_subject": "%(organisation_name)s - Kitsu: password changed",
        "auth_password_changed_by_admin_title": "Password Changed",
        "auth_password_changed_by_admin_body": """<p>Hello %(first_name)s,</p>
<p>Your password was changed at this date: %(time_string)s.</p>
<p>The IP of the user who changed your password is: %(person_IP)s.</p>
<p>If you don't know the person who changed the password, please contact our support team.</p>
""",
        # Auth: Two factor authentication disabled by admin
        "auth_2fa_disabled_by_admin_subject": "%(organisation_name)s - Kitsu: two factor authentication disabled",
        "auth_2fa_disabled_by_admin_title": "Two Factor Authentication Disabled",
        "auth_2fa_disabled_by_admin_body": """<p>Hello %(first_name)s,</p>
<p>Your two factor authentication was disabled at this date: %(time_string)s.</p>
<p>The IP of the user who disabled your two factor authentication is: %(person_IP)s.</p>
<p>If you don't know the person who disabled the two factor authentication, please contact our support team.</p>
""",
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
        "auth_otp_subject": "%(organisation_name)s - Kitsu : votre code de vérification",
        "auth_otp_title": "Votre code de vérification",
        "auth_otp_body": """<p>Bonjour %(first_name)s,</p>

<p>Votre code de vérification est : <strong>%(otp)s</strong></p>

<p>Ce mot de passe à usage unique expire dans 5 minutes. Ensuite, vous devrez en demander un nouveau.
Cet e-mail a été envoyé à la date : %(time_string)s.
L'IP de la personne ayant fait la demande est : %(person_IP)s.</p>
""",
        "auth_password_changed_subject": "%(organisation_name)s - Kitsu : mot de passe modifié",
        "auth_password_changed_title": "Mot de passe modifié",
        "auth_password_changed_body": """<p>Bonjour %(first_name)s,</p>

<p>Vous avez modifié votre mot de passe avec succès à la date : %(time_string)s.</p>
<p>Votre adresse IP lors du changement est : %(person_IP)s.</p>
""",
        "auth_password_recovery_subject": "%(organisation_name)s - Kitsu : récupération de mot de passe",
        "auth_password_recovery_title": "Récupération de mot de passe",
        "auth_password_recovery_body": """<p>Bonjour %(first_name)s,</p>

<p>Vous avez demandé une réinitialisation de mot de passe. Cliquez sur le bouton suivant pour le modifier :</p>

<p class="cta"><a class="button" href="%(reset_url)s">Changer votre mot de passe</a></p>

<p>Ce lien expire dans 2 heures. Ensuite, vous devrez faire une nouvelle demande.
Cet e-mail a été envoyé à la date : %(time_string)s.
L'IP de la personne ayant fait la demande est : %(person_IP)s.</p>
""",
        "auth_invitation_subject": "Vous êtes invité par %(organisation_name)s à rejoindre leur plateforme Kitsu",
        "auth_invitation_title": "Bienvenue sur Kitsu",
        "auth_invitation_body": """<p>Bonjour %(first_name)s,</p>
<p>Vous êtes invité par %(organisation_name)s à rejoindre leur équipe sur Kitsu.</p>
<p>Votre identifiant : <strong>%(email)s</strong></p>
<p>Définissez votre mot de passe pour continuer :</p>
<p class="cta"><a class="button" href="%(reset_url)s">Définir votre mot de passe</a></p>
""",
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
        "auth_otp_subject": "%(organisation_name)s - Kitsu: tu código de verificación",
        "auth_otp_title": "Tu código de verificación",
        "auth_otp_body": """<p>Hola %(first_name)s,</p>

<p>Tu código de verificación es: <strong>%(otp)s</strong></p>

<p>Esta contraseña de un solo uso caduca en 5 minutos. Después tendrás que solicitar una nueva.
Este correo se envió en esta fecha: %(time_string)s.
La IP de la persona que lo solicitó es: %(person_IP)s.</p>
""",
        "auth_password_changed_subject": "%(organisation_name)s - Kitsu: contraseña cambiada",
        "auth_password_changed_title": "Contraseña cambiada",
        "auth_password_changed_body": """<p>Hola %(first_name)s,</p>

<p>Has cambiado tu contraseña correctamente en esta fecha: %(time_string)s.</p>
<p>Tu IP al cambiar la contraseña es: %(person_IP)s.</p>
""",
        "auth_password_recovery_subject": "%(organisation_name)s - Kitsu: recuperación de contraseña",
        "auth_password_recovery_title": "Recuperación de contraseña",
        "auth_password_recovery_body": """<p>Hola %(first_name)s,</p>

<p>Has solicitado restablecer tu contraseña. Haz clic en el siguiente botón para cambiarla:</p>

<p class="cta"><a class="button" href="%(reset_url)s">Cambiar tu contraseña</a></p>

<p>Este enlace caduca en 2 horas. Después tendrás que solicitar un nuevo restablecimiento.
Este correo se envió en esta fecha: %(time_string)s.
La IP de la persona que lo solicitó es: %(person_IP)s.</p>
""",
        "auth_invitation_subject": "Has sido invitado por %(organisation_name)s a unirte a su plataforma Kitsu",
        "auth_invitation_title": "Bienvenido a Kitsu",
        "auth_invitation_body": """<p>Hola %(first_name)s,</p>
<p>Has sido invitado por %(organisation_name)s a unirte a su equipo en Kitsu.</p>
<p>Tu inicio de sesión es: <strong>%(email)s</strong></p>
<p>Establece tu contraseña para continuar:</p>
<p class="cta"><a class="button" href="%(reset_url)s">Establecer tu contraseña</a></p>
""",
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
        "auth_otp_subject": "%(organisation_name)s - Kitsu: 認証コード",
        "auth_otp_title": "認証コード",
        "auth_otp_body": """<p>%(first_name)s 様</p>

<p>認証コードは <strong>%(otp)s</strong> です。</p>

<p>このワンタイムパスワードは5分で失効します。その後は新しいコードをリクエストしてください。
送信日時: %(time_string)s。
リクエスト元のIP: %(person_IP)s。</p>
""",
        "auth_password_changed_subject": "%(organisation_name)s - Kitsu: パスワードを変更しました",
        "auth_password_changed_title": "パスワード変更完了",
        "auth_password_changed_body": """<p>%(first_name)s 様</p>

<p>パスワードを正常に変更しました。変更日時: %(time_string)s。</p>
<p>変更時のIP: %(person_IP)s。</p>
""",
        "auth_password_recovery_subject": "%(organisation_name)s - Kitsu: パスワードのリセット",
        "auth_password_recovery_title": "パスワードのリセット",
        "auth_password_recovery_body": """<p>%(first_name)s 様</p>

<p>パスワードのリセットをリクエストされました。以下のボタンからパスワードを変更してください。</p>

<p class="cta"><a class="button" href="%(reset_url)s">パスワードを変更</a></p>

<p>このリンクは2時間で失効します。その後は再度リセットをリクエストしてください。
送信日時: %(time_string)s。
リクエスト元のIP: %(person_IP)s。</p>
""",
        "auth_invitation_subject": "%(organisation_name)s から Kitsu への招待",
        "auth_invitation_title": "Kitsu へようこそ",
        "auth_invitation_body": """<p>%(first_name)s 様</p>
<p>%(organisation_name)s より Kitsu のチームに参加する招待が届きました。</p>
<p>ログイン: <strong>%(email)s</strong></p>
<p>続行するにはパスワードを設定してください:</p>
<p class="cta"><a class="button" href="%(reset_url)s">パスワードを設定</a></p>
""",
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
        "auth_otp_subject": "%(organisation_name)s - Kitsu: Ihr Bestätigungscode",
        "auth_otp_title": "Ihr Bestätigungscode",
        "auth_otp_body": """<p>Hallo %(first_name)s,</p>

<p>Ihr Bestätigungscode lautet: <strong>%(otp)s</strong></p>

<p>Dieses Einmalpasswort läuft nach 5 Minuten ab. Danach müssen Sie einen neuen anfordern.
Diese E-Mail wurde am %(time_string)s gesendet.
Die IP der anfragenden Person ist: %(person_IP)s.</p>
""",
        "auth_password_changed_subject": "%(organisation_name)s - Kitsu: Passwort geändert",
        "auth_password_changed_title": "Passwort geändert",
        "auth_password_changed_body": """<p>Hallo %(first_name)s,</p>

<p>Sie haben Ihr Passwort erfolgreich am %(time_string)s geändert.</p>
<p>Ihre IP bei der Änderung war: %(person_IP)s.</p>
""",
        "auth_password_recovery_subject": "%(organisation_name)s - Kitsu: Passwort-Wiederherstellung",
        "auth_password_recovery_title": "Passwort-Wiederherstellung",
        "auth_password_recovery_body": """<p>Hallo %(first_name)s,</p>

<p>Sie haben eine Passwort-Zurücksetzung angefordert. Klicken Sie auf die Schaltfläche unten, um Ihr Passwort zu ändern:</p>

<p class="cta"><a class="button" href="%(reset_url)s">Passwort ändern</a></p>

<p>Dieser Link läuft nach 2 Stunden ab. Danach müssen Sie eine neue Anfrage stellen.
Diese E-Mail wurde am %(time_string)s gesendet.
Die IP der anfragenden Person ist: %(person_IP)s.</p>
""",
        "auth_invitation_subject": "Sie wurden von %(organisation_name)s eingeladen, der Kitsu-Plattform beizutreten",
        "auth_invitation_title": "Willkommen bei Kitsu",
        "auth_invitation_body": """<p>Hallo %(first_name)s,</p>
<p>Sie wurden von %(organisation_name)s eingeladen, ihrem Team auf Kitsu beizutreten.</p>
<p>Ihre Anmeldung: <strong>%(email)s</strong></p>
<p>Setzen Sie Ihr Passwort, um fortzufahren:</p>
<p class="cta"><a class="button" href="%(reset_url)s">Passwort setzen</a></p>
""",
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
        "auth_otp_subject": "%(organisation_name)s - Kitsu: uw verificatiecode",
        "auth_otp_title": "Uw verificatiecode",
        "auth_otp_body": """<p>Hallo %(first_name)s,</p>

<p>Uw verificatiecode is: <strong>%(otp)s</strong></p>

<p>Dit eenmalige wachtwoord verloopt na 5 minuten. Daarna moet u een nieuwe aanvragen.
Deze e-mail is verzonden op: %(time_string)s.
Het IP-adres van de aanvrager is: %(person_IP)s.</p>
""",
        "auth_password_changed_subject": "%(organisation_name)s - Kitsu: wachtwoord gewijzigd",
        "auth_password_changed_title": "Wachtwoord gewijzigd",
        "auth_password_changed_body": """<p>Hallo %(first_name)s,</p>

<p>U heeft uw wachtwoord succesvol gewijzigd op: %(time_string)s.</p>
<p>Uw IP-adres bij de wijziging was: %(person_IP)s.</p>
""",
        "auth_password_recovery_subject": "%(organisation_name)s - Kitsu: wachtwoordherstel",
        "auth_password_recovery_title": "Wachtwoordherstel",
        "auth_password_recovery_body": """<p>Hallo %(first_name)s,</p>

<p>U heeft een wachtwoordreset aangevraagd. Klik op de onderstaande knop om uw wachtwoord te wijzigen:</p>

<p class="cta"><a class="button" href="%(reset_url)s">Wachtwoord wijzigen</a></p>

<p>Deze link verloopt na 2 uur. Daarna moet u een nieuwe aanvraag doen.
Deze e-mail is verzonden op: %(time_string)s.
Het IP-adres van de aanvrager is: %(person_IP)s.</p>
""",
        "auth_invitation_subject": "U bent door %(organisation_name)s uitgenodigd om deel te nemen aan hun Kitsu-platform",
        "auth_invitation_title": "Welkom bij Kitsu",
        "auth_invitation_body": """<p>Hallo %(first_name)s,</p>
<p>U bent door %(organisation_name)s uitgenodigd om deel te nemen aan hun team op Kitsu.</p>
<p>Uw inloggegevens: <strong>%(email)s</strong></p>
<p>Stel uw wachtwoord in om door te gaan:</p>
<p class="cta"><a class="button" href="%(reset_url)s">Wachtwoord instellen</a></p>
""",
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
        "auth_otp_subject": "%(organisation_name)s - Kitsu：您的验证码",
        "auth_otp_title": "您的验证码",
        "auth_otp_body": """<p>您好 %(first_name)s，</p>

<p>您的验证码是：<strong>%(otp)s</strong></p>

<p>此一次性密码将在 5 分钟后失效，之后您需要重新请求。
此邮件发送时间：%(time_string)s。
请求者 IP：%(person_IP)s。</p>
""",
        "auth_password_changed_subject": "%(organisation_name)s - Kitsu：密码已修改",
        "auth_password_changed_title": "密码已修改",
        "auth_password_changed_body": """<p>您好 %(first_name)s，</p>

<p>您已成功于 %(time_string)s 修改密码。</p>
<p>修改时的 IP：%(person_IP)s。</p>
""",
        "auth_password_recovery_subject": "%(organisation_name)s - Kitsu：找回密码",
        "auth_password_recovery_title": "找回密码",
        "auth_password_recovery_body": """<p>您好 %(first_name)s，</p>

<p>您已请求重置密码。请点击下方按钮修改密码：</p>

<p class="cta"><a class="button" href="%(reset_url)s">修改密码</a></p>

<p>此链接将在 2 小时后失效，之后需重新请求。
此邮件发送时间：%(time_string)s。
请求者 IP：%(person_IP)s。</p>
""",
        "auth_invitation_subject": "%(organisation_name)s 邀请您加入 Kitsu 平台",
        "auth_invitation_title": "欢迎使用 Kitsu",
        "auth_invitation_body": """<p>您好 %(first_name)s，</p>
<p>%(organisation_name)s 邀请您加入他们在 Kitsu 的团队。</p>
<p>您的登录名：<strong>%(email)s</strong></p>
<p>请设置密码以继续：</p>
<p class="cta"><a class="button" href="%(reset_url)s">设置密码</a></p>
""",
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
        "auth_otp_subject": "%(organisation_name)s - Kitsu: seu código de verificação",
        "auth_otp_title": "Seu código de verificação",
        "auth_otp_body": """<p>Olá %(first_name)s,</p>

<p>Seu código de verificação é: <strong>%(otp)s</strong></p>

<p>Esta senha de uso único expira em 5 minutos. Depois, você precisará solicitar uma nova.
Este e-mail foi enviado em: %(time_string)s.
O IP de quem solicitou é: %(person_IP)s.</p>
""",
        "auth_password_changed_subject": "%(organisation_name)s - Kitsu: senha alterada",
        "auth_password_changed_title": "Senha alterada",
        "auth_password_changed_body": """<p>Olá %(first_name)s,</p>

<p>Você alterou sua senha com sucesso em: %(time_string)s.</p>
<p>Seu IP ao alterar a senha foi: %(person_IP)s.</p>
""",
        "auth_password_recovery_subject": "%(organisation_name)s - Kitsu: recuperação de senha",
        "auth_password_recovery_title": "Recuperação de senha",
        "auth_password_recovery_body": """<p>Olá %(first_name)s,</p>

<p>Você solicitou a redefinição de senha. Clique no botão abaixo para alterá-la:</p>

<p class="cta"><a class="button" href="%(reset_url)s">Alterar sua senha</a></p>

<p>Este link expira em 2 horas. Depois, você precisará fazer uma nova solicitação.
Este e-mail foi enviado em: %(time_string)s.
O IP de quem solicitou é: %(person_IP)s.</p>
""",
        "auth_invitation_subject": "Você foi convidado por %(organisation_name)s para participar da plataforma Kitsu",
        "auth_invitation_title": "Bem-vindo ao Kitsu",
        "auth_invitation_body": """<p>Olá %(first_name)s,</p>
<p>Você foi convidado por %(organisation_name)s para participar da equipe no Kitsu.</p>
<p>Seu login: <strong>%(email)s</strong></p>
<p>Defina sua senha para continuar:</p>
<p class="cta"><a class="button" href="%(reset_url)s">Definir sua senha</a></p>
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
