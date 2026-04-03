from django.urls import path

from . import views


urlpatterns = [
    path('', views.home, name='home'),
    path('hats/', views.hats_constructor, name='hats_constructor'),
    path('jewelry/', views.jewelry_constructor, name='jewelry_constructor'),
    path('api/tryon/', views.tryon_api, name='tryon_api'),
    path('api/master-requests/', views.master_request_api, name='master_request_api'),
    path('contact/', views.contact, name='contact'),
    path('registration/', views.registration, name='registration'),
    path('login/', views.login, name='login'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('logout/', views.logout, name='logout'),
    path('about05/', views.about05, name='about05'),
    path('account/', views.account, name='account'),
    path('gallery/', views.gallery, name='gallery'),
    path('gallery/toggle/<int:work_id>/', views.toggle_gallery_visibility, name='toggle_gallery_visibility'),
    path('gallery/like/<int:work_id>/', views.toggle_gallery_like, name='toggle_gallery_like'),
    path('gallery/comment/<int:work_id>/', views.add_gallery_comment, name='add_gallery_comment'),
    path('gallery/comment-vote/<int:comment_id>/', views.vote_gallery_comment, name='vote_gallery_comment'),
    path('gallery/copy/<int:work_id>/', views.copy_gallery_work, name='copy_gallery_work'),
    path('account/update-work-title/<int:work_id>/', views.update_work_title, name='update_work_title'),
    path('account/delete-work/<int:work_id>/', views.delete_work, name='delete_work'),
    path('extra-generations/', views.extra_generations, name='extra_generations'),
    path('master-chat/', views.master_chat, name='master_chat'),
    path('master-recovery-requests/', views.master_recovery_requests, name='master_recovery_requests'),
    path('privacy/', views.privacy, name='privacy'),
]
