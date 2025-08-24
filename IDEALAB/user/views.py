import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model, authenticate, login, logout

User = get_user_model()

def _json_body(request):
    try:
        return json.loads(request.body.decode('utf-8'))
    except Exception:
        return {}

@csrf_exempt
@require_http_methods(["POST"])
def signup(request):
    data = _json_body(request)
    name = data.get('name')
    email = data.get('email')
    nickname = data.get('nickname')
    password = data.get('password')

    if not all([name, email, nickname, password]):
        return JsonResponse({"ok": False, "error": "필수 필드 누락"}, status=400)

    if User.objects.filter(email=email).exists():
        return JsonResponse({"ok": False, "error": "이미 사용 중인 이메일입니다."}, status=409)
    if User.objects.filter(nickname=nickname).exists():
        return JsonResponse({"ok": False, "error": "이미 사용 중인 닉네임입니다."}, status=409)

    user = User.objects.create_user(email=email, password=password, name=name, nickname=nickname)
    return JsonResponse({"ok": True, "user": {"id": user.id, "email": user.email, "name": user.name, "nickname": user.nickname}}, status=201)

@csrf_exempt
@require_http_methods(["POST"])
def login_view(request):
    data = _json_body(request)
    email = data.get('email')
    password = data.get('password')

    if not all([email, password]):
        return JsonResponse({"ok": False, "error": "이메일/비밀번호를 확인하세요."}, status=400)

    user = authenticate(request, email=email, password=password)
    if user is None:
        return JsonResponse({"ok": False, "error": "로그인 실패(이메일 또는 비밀번호 확인)."}, status=401)

    login(request, user)
    return JsonResponse({"ok": True, "user": {"id": user.id, "email": user.email, "name": user.name, "nickname": user.nickname}})

@csrf_exempt
@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return JsonResponse({"ok": True})
