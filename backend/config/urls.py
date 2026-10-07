from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from energy.views import (
    AdminLoginView,
    AlertAcknowledgeView,
    NotificationTestView,
    SubscriberProfileView,
    AdminOverviewView,
    AssistantView,
    BudgetView,
    DashboardViewSet,
    FlutterwaveRedirectView,
    FlutterwaveWebhookView,
    ManualTokenApplyView,
    ManualTokenIssueView,
    NewsViewSet,
    PawaPayCallbackView,
    PawaPayDepositStatusView,
    PaymentInitiateView,
    ReceiptView,
    RelayCommandView,
    SubscriberLoginView,
    SubscriberLogoutView,
    TelemetryIngestView,
    TokenRefreshView,
)

router = DefaultRouter()
router.register("dashboard", DashboardViewSet, basename="dashboard")
router.register("news", NewsViewSet, basename="news")


def frontend_file(request, file_name="index.html"):
    root = (Path(settings.BASE_DIR).parent / "dist" / "public").resolve()
    target = (root / file_name).resolve()
    if root not in target.parents and target != root:
        raise Http404
    if not target.exists() or not target.is_file():
        target = root / "index.html"
    if not target.exists():
        raise Http404
    return FileResponse(target.open("rb"))


urlpatterns = [
    path("api/iot/telemetry", TelemetryIngestView.as_view(), name="iot-telemetry"),
    path("api/auth/subscriber/login/", SubscriberLoginView.as_view(), name="subscriber-login"),
    path("api/auth/admin/login/", AdminLoginView.as_view(), name="admin-login"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("api/auth/subscriber/logout/", SubscriberLogoutView.as_view(), name="subscriber-logout"),
    path("api/recharges/manual/issue/", ManualTokenIssueView.as_view(), name="manual-token-issue"),
    path("api/recharges/manual/apply/", ManualTokenApplyView.as_view(), name="manual-token-apply"),
    path("api/payments/initiate/", PaymentInitiateView.as_view(), name="payment-initiate"),
    path("api/payments/flutterwave/webhook/", FlutterwaveWebhookView.as_view(), name="flutterwave-webhook"),
    path("api/payments/flutterwave/verify/", FlutterwaveRedirectView.as_view(), name="flutterwave-verify"),
    path("api/payments/pawapay/callback/", PawaPayCallbackView.as_view(), name="pawapay-callback"),
    path("api/payments/pawapay/status/<str:deposit_id>/", PawaPayDepositStatusView.as_view(), name="pawapay-status"),
    path("api/relay/commands/", RelayCommandView.as_view(), name="relay-commands"),
    path("api/assistant/", AssistantView.as_view(), name="assistant"),
    path("api/alerts/<int:alert_id>/ack/", AlertAcknowledgeView.as_view(), name="alert-ack"),
    path("api/profile/", SubscriberProfileView.as_view(), name="profile"),
    path("api/notifications/test/", NotificationTestView.as_view(), name="notification-test"),
    path("api/budget/", BudgetView.as_view(), name="budget"),
    path("api/admin/overview/", AdminOverviewView.as_view(), name="admin-overview"),
    path("api/receipts/<str:recharge_id>/", ReceiptView.as_view(), name="receipt"),
    path("api/", include(router.urls)),
    re_path(r"^(?!api/|ws/)(?P<file_name>.*)$", frontend_file, name="frontend"),
]
