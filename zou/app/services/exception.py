from werkzeug.exceptions import NotFound, BadRequest, Forbidden


class EpisodeNotFoundException(NotFound):
    pass


class SequenceNotFoundException(NotFound):
    pass


class ShotNotFoundException(NotFound):
    pass


class SceneNotFoundException(NotFound):
    pass


class AssetNotFoundException(NotFound):
    pass


class AssetInstanceNotFoundException(NotFound):
    pass


class AssetTypeNotFoundException(NotFound):
    pass


class AttachmentFileNotFoundException(NotFound):
    pass


class TaskNotFoundException(NotFound):
    pass


class DepartmentNotFoundException(NotFound):
    pass


class TaskStatusNotFoundException(NotFound):
    pass


class TaskTypeNotFoundException(NotFound):
    pass


class PersonNotFoundException(NotFound):
    pass


class ProjectNotFoundException(NotFound):
    pass


class WorkingFileNotFoundException(NotFound):
    pass


class OutputFileNotFoundException(NotFound):
    pass


class SoftwareNotFoundException(NotFound):
    pass


class OutputTypeNotFoundException(NotFound):
    pass


class PreviewFileNotFoundException(NotFound):
    pass


class CommentNotFoundException(NotFound):
    pass


class NewsNotFoundException(NotFound):
    pass


class EntityNotFoundException(NotFound):
    pass


class EntityLinkNotFoundException(NotFound):
    pass


class EntityTypeNotFoundException(NotFound):
    pass


class BuildJobNotFoundException(NotFound):
    pass


class PlaylistNotFoundException(NotFound):
    pass


class SearchFilterNotFoundException(NotFound):
    pass


class NotificationNotFoundException(NotFound):
    pass


class SubscriptionNotFoundException(NotFound):
    pass


class MetadataDescriptorNotFoundException(NotFound):
    pass


class MalformedFileTreeException(BadRequest):
    pass


class WrongFileTreeFileException(BadRequest):
    pass


class WrongPathFormatException(BadRequest):
    pass


class NoOutputFileException(Exception):
    pass


class NoAuthStrategyConfigured(Exception):
    pass


class WrongUserException(Exception):
    pass


class WrongPasswordException(BadRequest):
    pass


class MissingOTPException(BadRequest):
    def __init__(
        self,
        preferred_two_factor_authentication,
        two_factor_authentication_enabled,
    ):
        self.preferred_two_factor_authentication = (
            preferred_two_factor_authentication
        )
        self.two_factor_authentication_enabled = (
            two_factor_authentication_enabled
        )


class WrongOTPException(BadRequest):
    pass


class TOTPAlreadyEnabledException(BadRequest):
    description = "TOTP already enabled."


class TOTPNotEnabledException(BadRequest):
    description = "TOTP not enabled."


class TwoFactorAuthenticationNotEnabledException(BadRequest):
    description = "Two factor authentication not enabled for this user."


class FIDONoPreregistrationException(BadRequest):
    description = "No preregistration before."


class FIDOServerException(BadRequest):
    description = (
        "FIDO server exception your registration response is probably wrong."
    )


class FIDONotEnabledException(BadRequest):
    description = "FIDO not enabled."


class EmailOTPAlreadyEnabledException(BadRequest):
    description = "OTP by email already enabled."


class EmailOTPNotEnabledException(BadRequest):
    description = "OTP by email not enabled."


class NoTwoFactorAuthenticationEnabled(BadRequest):
    description = "No two factor authentication enabled."


class TooMuchLoginFailedAttemps(BadRequest):
    pass


class UserCantConnectDueToNoFallback(BadRequest):
    pass


class UnactiveUserException(BadRequest):
    description = "User is unactive."


class WrongDateFormatException(BadRequest):
    description = "Wrong date format."


class EntryAlreadyExistsException(BadRequest):
    pass


class ArgumentsException(BadRequest):
    pass


class WrongIdFormatException(BadRequest):
    description = "One of the ID sent in parameter is not properly formatted."


class WrongParameterException(BadRequest):
    pass


class ModelWithRelationsDeletionException(BadRequest):
    pass


class EditNotFoundException(NotFound):
    pass


class StatusAutomationNotFoundException(NotFound):
    pass


class WrongTaskTypeForEntityException(BadRequest):
    pass


class IsUserLimitReachedException(Exception):
    pass
