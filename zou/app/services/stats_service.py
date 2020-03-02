from zou.app.models.preview_file import PreviewFile
from zou.app.models.comment import Comment


def get_main_stats():
    return {
        "number_of_video_previews":
            PreviewFile.query.filter(PreviewFile.extension == "mp4").count(),
        "number_of_picture_previews":
            PreviewFile.query.filter(PreviewFile.extension == "png").count(),
        "number_of_model_previews":
            PreviewFile.query.filter(PreviewFile.extension == "obj").count(),
        "number_of_comments":
            Comment.query.count()
    }
