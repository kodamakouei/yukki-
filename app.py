import streamlit as st
from google import genai
import base64
import json
import requests
import streamlit.components.v1 as components
import os
import time
import io
from PIL import Image
from streamlit_drawable_canvas import st_canvas
from google.genai.types import Part

# =========================================
#  システムプロンプト
# =========================================
SYSTEM_PROMPT = """
あなたは教育的な目的を持つ AI アシスタントです。
ユーザーの質問に対して以下のルールに従ってできるだけかみ砕いてわかりやすく応答してください。
1⃣知識・定義直接答えます。
2⃣思考・計算問題答えは教えず、解法のヒントのみを示します。
3⃣途中式正誤を判定し、優しく導きます。
4⃣専門用語ステップごとに区切り、専門用語について知っているか確認します。知らなかった場合は、小学生にもわかるように、図や擬音などの表現、例となる面白い文を積極的に使ってその場で説明します。
5⃣説明は砕けた会話口調でお願いします。
6⃣いきなりステップを全部出さないでください。「ここで、～～について知っていますか？」のところでいったん表示するのをやめてください。
7⃣専門用語や途中の過程の分からない部分について説明されたときは、できるだけ詳しく説明してください。だからと言ってその説明を聞いている人に読むのを飽きさせてしまうような説明はやめてください。
8⃣ヒント・ギブアップ要請への対応:
- 【ヒント1要請】: 答えや計算式は出さず、この問題を解くための「着眼点（何に注目すべきか）」だけを優しく短めに教えてください。
- 【ヒント2要請】: 答えは出さず、この問題で「使うべき公式・考え方・定理」を優しく教えてください。
- 【ヒント3要請】: 最後の答えは出さず、「解法の最初の一歩（式変形の1行目など）」を具体的に示して、続きを自分で解けるように導いてください。
- 【ギブアップ要請】: ここまで一生懸命考えた努力を惜しみなく褒めた上で、完全な答えとステップバイステップの丁寧な全解説を優しく教えてください。
9⃣学習サポート機能への対応:
- 【類題出題要請】: 直前の問題と同じ解法・公式パターンを使い、数値や設定を変えた「新しい類題」を1問出題してください。指定された難易度に応じた問題文のみを提示し、答えや解説は書かずに「さあ、解いてみてね！」と元気よく促してください。
- 【手書きメモ添削要請】: ユーザーの手書き途中式やメモの画像を解析し、赤ペン先生のように「どこまで合っているか」を褒め、間違えている部分があればその箇所と正しい考え方を優しく教えてください。
- 【理解度クイズ出題要請】: 直前の問題の要点や重要公式に関する「3択クイズ」を1問作成してください。出力は必ず以下の書式を含めてください：
  【問題】（ここに問題文）
  【A】（選択肢1）
  【B】（選択肢2）
  【C】（選択肢3）
- 【ニガテ帳まとめ要請】: これまでの学習履歴を振り返り、つまずいたポイント、重要公式・定理、ユッキーからの応援アドバイスをMarkdown形式の「復習まとめノート」として綺麗に整理して出力してください。
"""

# =========================================
# APIキー読み込みと画像Base64変換関数
# =========================================
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = ""

# =========================================
# ユーザーデータ永続化モジュール (JSONストレージ)
# =========================================
USER_DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "users")
os.makedirs(USER_DATA_DIR, exist_ok=True)

def get_current_user_id():
    """現在ログイン中のユーザーID（またはゲストID）を返す"""
    if getattr(st.user, "is_logged_in", False):
        return getattr(st.user, "sub", None) or getattr(st.user, "email", "google_user")
    return "guest_user"

def get_user_data_path(user_id):
    safe_id = "".join(c for c in str(user_id) if c.isalnum() or c in ("-", "_"))
    return os.path.join(USER_DATA_DIR, f"{safe_id}.json")

def load_user_data(user_id):
    path = get_user_data_path(user_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"ユーザーデータ読み込みエラー: {e}")
    return {
        "stars": 0,
        "stamps": 0,
        "summary_note": "",
        "last_active": ""
    }

def save_user_data(user_id):
    path = get_user_data_path(user_id)
    data = {
        "user_id": user_id,
        "stars": st.session_state.get("stars", 0),
        "stamps": st.session_state.get("stamps", 0),
        "summary_note": st.session_state.get("summary_note", ""),
        "last_active": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"ユーザーデータ保存エラー: {e}")

def is_auth_configured():
    """Google認証がsecrets.tomlに設定されているか判定"""
    try:
        return "auth" in st.secrets
    except Exception:
        return False
    

def get_base64_image(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as f:
            data = f.read()
            return base64.b64encode(data).decode("utf-8")
    return ""

# 画像の準備
IMG_ICON_B64 = get_base64_image("yukki-close.jpg")
IMG_OPEN_B64 = get_base64_image("yukki-open.jpg")
IMG_CLOSE_B64 = get_base64_image("yukki-close.jpg")

# サイドバーの推奨幅
SIDEBAR_FIXED_WIDTH = "340px"

# =========================================
# Streamlit UI 設定とカスタム CSS
# =========================================
st.set_page_config(
    page_title="疑似教師AIユッキー",
    layout="wide",
    initial_sidebar_state="expanded", 
    menu_items={'About': None, 'Report a bug': None, 'Get help': None}
)

# カスタム CSS で全体の見た目をモダンに
st.markdown(f"""
<style>
/* Streamlitヘッダーを非表示 */
header {{ visibility: hidden; }}

/* サイドバーのリサイズハンドルを非表示 */
[data-testid="stSidebarContent"] + div {{
    display: none !important;
}}

/* サイドバーのコンテンツコンテナ */
[data-testid="stSidebarContent"] {{
    width: {SIDEBAR_FIXED_WIDTH} !important;
    min-width: {SIDEBAR_FIXED_WIDTH} !important;
    max-width: {SIDEBAR_FIXED_WIDTH} !important;
    background-color: #f7f9fc;
    border-right: 1px solid #e2e8f0;
    overflow-x: hidden !important; 
    overflow-y: auto !important; 
}}

/* サイドバーを閉じるボタンを非表示 */
[data-testid="stSidebarCollapseButton"] {{
    display: none !important;
}}

/* 全体フォントとスタイル調整 */
body, .stMarkdown {{
    font-family: 'Outfit', 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}}

.stApp {{
    background-color: #ffffff;
}}

/* チャットメッセージの丸みと背景 */
.stChatMessage {{
    border-radius: 12px;
    padding: 12px;
    margin-bottom: 10px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.02);
}}
</style>
""", unsafe_allow_html=True)

# ---- セッション初期化 ----
if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=API_KEY) if API_KEY else None

if "chat" not in st.session_state:
    if st.session_state.client:
        config = {
            "system_instruction": SYSTEM_PROMPT,
            "temperature": 0.3
        }
        st.session_state.chat = st.session_state.client.chats.create(
            model="gemini-2.5-flash",
            config=config
        )
    else:
        st.session_state.chat = None

if "messages" not in st.session_state:
    st.session_state.messages = []

if "latest_assistant_message" not in st.session_state:
    st.session_state.latest_assistant_message = ""

if "msg_counter" not in st.session_state:
    st.session_state.msg_counter = 0

if "hint_level" not in st.session_state:
    st.session_state.hint_level = 1

# ユーザーごとの永続化データの読み込み
current_user_id = get_current_user_id()
if "loaded_user_id" not in st.session_state or st.session_state.loaded_user_id != current_user_id:
    saved_data = load_user_data(current_user_id)
    st.session_state.stars = saved_data.get("stars", 0)
    st.session_state.stamps = saved_data.get("stamps", 0)
    st.session_state.summary_note = saved_data.get("summary_note", "")
    st.session_state.loaded_user_id = current_user_id

if "stars" not in st.session_state:
    st.session_state.stars = 0

if "stamps" not in st.session_state:
    st.session_state.stamps = 0

if "canvas_key_num" not in st.session_state:
    st.session_state.canvas_key_num = 0

if "show_gacha" not in st.session_state:
    st.session_state.show_gacha = False

if "summary_note" not in st.session_state:
    st.session_state.summary_note = ""

# 📸 サイドバー
with st.sidebar:
    # 🔑 Googleログイン & プロフィール
    is_logged_in = getattr(st.user, "is_logged_in", False)
    if is_logged_in:
        user_name = getattr(st.user, "name", "ユーザー")
        user_email = getattr(st.user, "email", "")
        user_pic = getattr(st.user, "picture", "")

        st.markdown(f"""
        <div style="background: #ffffff; border: 1px solid #bbf7d0; border-radius: 12px; padding: 10px 12px; margin-top: 6px; margin-bottom: 12px; display: flex; align-items: center; gap: 10px; box-shadow: 0 2px 5px rgba(34, 197, 94, 0.1);">
            <img src="{user_pic if user_pic else 'https://www.gstatic.com/images/branding/product/1x/avatar_square_blue_512dp.png'}" style="width: 36px; height: 36px; border-radius: 50%; border: 2px solid #22c55e; object-fit: cover;" />
            <div style="overflow: hidden; flex: 1;">
                <div style="font-size: 13px; font-weight: bold; color: #15803d; white-space: nowrap; text-overflow: ellipsis; overflow: hidden;">{user_name}</div>
                <div style="font-size: 10px; color: #64748b; white-space: nowrap; text-overflow: ellipsis; overflow: hidden;">{user_email}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🚪 ログアウト", key="btn_logout", use_container_width=True):
            save_user_data(st.session_state.loaded_user_id)
            st.logout()
    else:
        if is_auth_configured():
            st.markdown("""
            <div style="background: #ffffff; border: 1px solid #fed7aa; border-radius: 12px; padding: 10px; margin-top: 6px; margin-bottom: 8px; text-align: center; box-shadow: 0 2px 5px rgba(249, 115, 22, 0.08);">
                <div style="font-size: 12px; font-weight: 600; color: #c2410c; margin-bottom: 6px;">Googleで学習データを同期</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("🔐 Googleでログイン", key="btn_google_login", use_container_width=True):
                st.login()
        else:
            with st.expander("🔐 Googleログインの設定", expanded=False):
                st.markdown("""
                <div style="font-size: 11px; line-height: 1.5; color: #475569;">
                <b>設定手順:</b><br>
                1. <a href="https://console.cloud.google.com/" target="_blank">Google Cloud Console</a> でOAuth 2.0クライアントを作成<br>
                2. 承認済みのリダイレクトURIに以下を登録:<br>
                <code>http://localhost:8501/oauth2callback</code><br>
                3. <code>.streamlit/secrets.toml.template</code> を元に <code>secrets.toml</code> を作成して入力
                </div>
                """, unsafe_allow_html=True)
            st.caption("※ 現在はゲストモードとして端末内にデータ保存中")

    st.markdown("<h3 style='text-align: center; color: #ff4b4b; margin-top: 10px;'>🎀 AIユッキー</h3>", unsafe_allow_html=True)
    
    # 口パク HTML コンポーネントの表示
    if IMG_ICON_B64 and IMG_OPEN_B64 and IMG_CLOSE_B64:
        text_to_speak = st.session_state.latest_assistant_message
        msg_id = f"msg_{st.session_state.msg_counter}"
        
        html_code = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    background-color: transparent;
                }}
                .avatar-container {{
                    position: relative;
                    width: 200px;
                    height: 200px;
                    margin-bottom: 15px;
                }}
                .avatar-img {{
                    width: 100%;
                    height: 100%;
                    border-radius: 50%;
                    border: 4px solid #ff4b4b;
                    object-fit: cover;
                    box-shadow: 0 8px 20px rgba(255, 75, 75, 0.2);
                    transition: transform 0.3s ease;
                }}
                .avatar-img.talking {{
                    animation: pulse 0.5s infinite alternate;
                }}
                @keyframes pulse {{
                    0% {{ transform: scale(1.0); }}
                    100% {{ transform: scale(1.03); }}
                }}
            </style>
        </head>
        <body>
            <div class="avatar-container">
                <img id="avatar" class="avatar-img" src="data:image/jpeg;base64,{IMG_ICON_B64}" alt="Yukki" />
            </div>
            
            <script>
                const imgIcon = "data:image/jpeg;base64,{IMG_ICON_B64}";
                const imgOpen = "data:image/jpeg;base64,{IMG_OPEN_B64}";
                const imgClose = "data:image/jpeg;base64,{IMG_CLOSE_B64}";
                const textData = {json.dumps(text_to_speak)};
                const currentMsgId = "{msg_id}";
                
                const avatar = document.getElementById("avatar");
                
                let lipSyncInterval = null;
                
                function cleanText(rawText) {{
                    if (!rawText) return "";
                    return rawText.replace(/[*#`_\\-]/g, '').trim();
                }}
                
                function startLipSync() {{
                    if (lipSyncInterval) clearInterval(lipSyncInterval);
                    avatar.classList.add("talking");
                    lipSyncInterval = setInterval(() => {{
                        avatar.src = Math.random() > 0.4 ? imgOpen : imgClose;
                    }}, 50);
                }}
                
                function stopLipSync() {{
                    if (lipSyncInterval) {{
                        clearInterval(lipSyncInterval);
                        lipSyncInterval = null;
                    }}
                    avatar.classList.remove("talking");
                    avatar.src = imgIcon;
                }}
                
                function speakText() {{
                    const cleaned = cleanText(textData);
                    if (!cleaned) return;
                    
                    window.speechSynthesis.cancel();
                    
                    const utterance = new SpeechSynthesisUtterance(cleaned);
                    const voices = window.speechSynthesis.getVoices();
                    const jaVoice = voices.find(v => v.lang.includes("ja"));
                    if (jaVoice) {{
                        utterance.voice = jaVoice;
                    }}
                    
                    utterance.rate = 1.05;
                    
                    utterance.onstart = () => {{
                        startLipSync();
                    }};
                    
                    utterance.onend = () => {{
                        stopLipSync();
                        if (window.parent.conversationMode) {{
                            setTimeout(() => {{
                                if (window.parent.startListening) {{
                                    window.parent.startListening();
                                }}
                            }}, 800);
                        }}
                    }};
                    
                    utterance.onerror = () => {{
                        stopLipSync();
                        if (window.parent.conversationMode) {{
                            setTimeout(() => {{
                                if (window.parent.startListening) {{
                                    window.parent.startListening();
                                }}
                            }}, 800);
                        }}
                    }};
                    
                    window.speechSynthesis.speak(utterance);
                }}
                
                if (textData) {{
                    setTimeout(() => {{
                        speakText();
                    }}, 600);
                }}
                
                if (typeof window.speechSynthesis !== 'undefined') {{
                    window.speechSynthesis.getVoices();
                }}
            </script>
        </body>
        </html>
        """
        components.html(html_code, height=290)
    else:
        st.warning("アバター画像が見つかりません。")

    # ⭐ がんばりスコア & スタンプカード
    st.markdown(f"""
    <div style="background: white; border: 1px solid #ffd1d1; border-radius: 12px; padding: 12px; margin-top: 10px; box-shadow: 0 2px 6px rgba(255, 75, 75, 0.08);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-size: 13px; font-weight: bold; color: #ff4b4b;">⭐ がんばりスコア</span>
            <span style="font-size: 14px; font-weight: bold; color: #d97706;">⭐ {st.session_state.stars}</span>
        </div>
        <div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">
            クリアスタンプ: {st.session_state.stamps % 5 if st.session_state.stamps % 5 != 0 or st.session_state.stamps == 0 else 5}/5 問
        </div>
        <div style="display: flex; justify-content: space-around; font-size: 18px; margin-bottom: 8px;">
            {' '.join(['🌸' if i < (5 if st.session_state.stamps > 0 and st.session_state.stamps % 5 == 0 else st.session_state.stamps % 5) else '⚪' for i in range(5)])}
        </div>
        <div style="font-size: 11px; font-style: italic; color: #ff6b6b; text-align: center; border-top: 1px dashed #fee2e2; padding-top: 6px;">
            {'「いっしょにがんばろ！」' if st.session_state.stars < 3 else ('「いい調子！その調子！」' if st.session_state.stars < 8 else '「天才すぎ！ユッキー大感激！💖」')}
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 📑 今日のニガテ帳・まとめカード生成
    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    if st.button("📑 今日のまとめノート作成", key="btn_make_summary", use_container_width=True):
        if len(st.session_state.messages) == 0:
            st.warning("まだ学習履歴がありません。問題を解いた後に押してね！")
        elif st.session_state.chat:
            with st.spinner("ユッキーが今日のまとめノートを作成中..."):
                summary_prompt = "【ニガテ帳まとめ要請】これまでの学習チャット履歴を振り返り、ユーザーがつまずきやすかったポイント、重要公式・定理、ユッキーからの応援アドバイスをMarkdown形式の「復習まとめノート」として綺麗に整理して出力してください。"
                try:
                    res = st.session_state.chat.send_message([summary_prompt])
                    st.session_state.summary_note = res.text if hasattr(res, "text") else str(res)
                    save_user_data(st.session_state.loaded_user_id)
                    st.session_state.messages.append({"role": "assistant", "content": f"📑 **【今日のまとめノート】** が完成したよ！サイドバーから保存してね！\n\n{st.session_state.summary_note}"})
                    st.session_state.latest_assistant_message = "今日のまとめノートが完成したよ！サイドバーからダウンロードできるよ！"
                    st.session_state.msg_counter += 1
                    st.rerun()
                except Exception as e:
                    st.error(f"作成エラー: {e}")

    if st.session_state.summary_note:
        st.download_button(
            label="💾 まとめノートを保存",
            data=st.session_state.summary_note,
            file_name="yukki_study_note.md",
            mime="text/markdown",
            use_container_width=True
        )

# =========================================
# メッセージ送信・AI対話 共通処理
# =========================================
def send_message_to_assistant(display_text, ai_prompt=None, attach_bytes=None, attach_file=None):
    """ユーザーメッセージを履歴に追加し、Geminiに送信して応答を保存・読み上げる共通処理"""
    st.session_state.messages.append({"role": "user", "content": display_text})

    prompt_to_send = ai_prompt if ai_prompt is not None else display_text
    contents_to_send = []

    if attach_file and attach_bytes:
        file_name = attach_file.name.lower()
        if file_name.endswith(('.png', '.jpg', '.jpeg', '.pdf')):
            try:
                file_part = Part.from_bytes(
                    data=attach_bytes,
                    mime_type=attach_file.type
                )
                contents_to_send.append(file_part)
            except Exception as e:
                print(f"ファイルデータの変換エラー: {e}")
        else:
            try:
                text_content = attach_bytes.decode("utf-8", errors="ignore")
                prompt_to_send = f"【添付ファイル名: {attach_file.name}】\n```\n{text_content}\n```\n\n{prompt_to_send}"
            except Exception as e:
                print(f"テキスト読み込みエラー: {e}")

    contents_to_send.append(prompt_to_send)

    if st.session_state.chat:
        try:
            response = st.session_state.chat.send_message(contents_to_send)
            response_text = response.text if hasattr(response, "text") else str(response)
        except Exception as e:
            response_text = f"Gemini APIエラー: {type(e).__name__} - {e}"
    else:
        response_text = "APIキーが設定されていないため応答できません。"

    st.session_state.messages.append({"role": "assistant", "content": response_text})
    st.session_state.latest_assistant_message = response_text
    st.session_state.msg_counter += 1
    st.rerun()

# =========================================
# メイン画面 UI
# =========================================
st.title("🎀 疑似教師AIユッキー")
st.caption("ユッキーが解説してくれます！入力欄左端の「＋」から画像を添付して質問できます。")

# ---------- ✍️ 手書きホワイトボード (途中式メモ・赤ペン添削) ----------
with st.expander("✍️ 手書きホワイトボード (計算メモ・赤ペン添削)", expanded=False):
    st.caption("マウスやタッチペンで途中式を書いて「🖍️ 添削して！」を押すと、ユッキーが赤ペン先生してくれます！")
    wb_col1, wb_col2 = st.columns([4, 1])
    with wb_col2:
        wb_color = st.color_picker("ペンの色", "#1e293b", key="wb_color_picker")
        wb_width = st.slider("線の太さ", 1, 10, 3, key="wb_width_slider")
        if st.button("🗑️ 全消去", key="btn_clear_wb", use_container_width=True):
            st.session_state.canvas_key_num += 1
            st.rerun()
    with wb_col1:
        canvas_result = st_canvas(
            fill_color="rgba(255, 255, 255, 0)",
            stroke_width=wb_width,
            stroke_color=wb_color,
            background_color="#ffffff",
            height=200,
            width=540,
            drawing_mode="freedraw",
            key=f"canvas_wb_{st.session_state.canvas_key_num}",
        )
    if st.button("🖍️ ユッキー、この途中式を添削して！", key="btn_submit_wb", use_container_width=True):
        if canvas_result is not None and canvas_result.image_data is not None:
            img_arr = canvas_result.image_data.astype('uint8')
            pil_img = Image.fromarray(img_arr, 'RGBA')
            buffered = io.BytesIO()
            pil_img.save(buffered, format="PNG")
            wb_bytes = buffered.getvalue()

            class CanvasUpload:
                name = "whiteboard.png"
                type = "image/png"

            send_message_to_assistant(
                display_text="✍️ **【手書きメモ添削】** 途中式を書いたよ！見てみて！",
                ai_prompt="【手書きメモ添削要請】ユーザーの手書き途中式・計算メモの画像です。どこまで合っているか優しく褒め、間違えている部分があれば赤ペン先生のように具体的にその箇所と理由を教えて、次のステップへ導いてください。",
                attach_bytes=wb_bytes,
                attach_file=CanvasUpload()
            )

# ---------- チャット履歴 ----------
for msg in st.session_state.messages:
    avatar_icon = "🧑" if msg["role"] == "user" else "yukki-icon.jpg"
    with st.chat_message(msg["role"], avatar=avatar_icon):
        st.markdown(msg["content"])

# ---------- カスタム CSS (＋ボタン化とレイアウト調整) ----------
st.markdown("""
<style>
/* チャット入力エリアを相対位置の基準にする */
div[data-testid="stChatInput"] {
    position: relative !important;
    width: 100% !important;
}

/* 入力エリアのテキスト入力欄の左側と右側に余白を作り、＋ボタンとマイクボタンのスペースを確保 */
div[data-testid="stChatInput"] textarea {
    padding-left: 46px !important;
    padding-right: 85px !important;
}

/* ファイルアップローダーをテキスト入力欄の左側に絶対配置 */
div[data-testid="stChatInput"] div[data-testid="stFileUploader"] {
    position: absolute !important;
    left: 8px !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
    width: 32px !important;
    height: 32px !important;
    padding: 0 !important;
    margin: 0 !important;
    z-index: 10;
    background: transparent !important;
}

/* ドラッグ＆ドロップエリア(section)を完全に丸い＋ボタンに整形 */
div[data-testid="stChatInput"] div[data-testid="stFileUploader"] section {
    padding: 0 !important;
    margin: 0 !important;
    height: 32px !important;
    width: 32px !important;
    min-height: 32px !important;
    border-radius: 50% !important;
    border: 2px solid #ff4b4b !important;
    background-color: #ffffff !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    overflow: hidden;
    cursor: pointer;
    box-shadow: 0 1px 4px rgba(255, 75, 75, 0.15);
    transition: all 0.2s ease;
}

div[data-testid="stChatInput"] div[data-testid="stFileUploader"] section:hover {
    background-color: #fff0f0 !important;
    border-color: #e03e3e !important;
}

div[data-testid="stChatInput"] div[data-testid="stFileUploader"] section:hover::after {
    color: #e03e3e !important;
}

/* デフォルトの「Browse files」や「Drag and drop」テキスト、アイコン類を完全に非表示にする */
div[data-testid="stChatInput"] div[data-testid="stFileUploader"] section * {
    display: none !important;
}

/* ＋マークを描画する */
div[data-testid="stChatInput"] div[data-testid="stFileUploader"] section::after {
    content: "+" !important;
    display: block !important;
    color: #ff4b4b !important;
    font-size: 20px !important;
    font-weight: bold !important;
    line-height: 1 !important;
    margin-top: -2px;
}

/* アップロードされた画像プレビューのスタイル */
.preview-box {
    position: fixed;
    bottom: 90px;
    left: 360px;
    background-color: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 6px 12px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    z-index: 9998;
    display: flex;
    align-items: center;
    gap: 8px;
}

@media (max-width: 768px) {
    .preview-box {
        left: 20px !important;
    }
}

/* ヒントバーのスタイリング */
.hint-bar-wrapper {
    margin-top: 18px;
    margin-bottom: 8px;
    padding: 8px 12px;
    background: #fff8f8;
    border-radius: 10px;
    border-left: 4px solid #ff4b4b;
}

.hint-bar-title {
    font-size: 13px;
    font-weight: 700;
    color: #e03e3e;
}

.hint-stage-badge {
    display: inline-block;
    background: #ff4b4b;
    color: white;
    font-size: 11px;
    font-weight: 600;
    padding: 1px 7px;
    border-radius: 10px;
    margin-left: 6px;
    vertical-align: middle;
}

.hint-bar-sub {
    font-size: 11px;
    color: #888888;
    margin-top: 2px;
}

/* ボタンのスタイル統一 */
div.stButton > button {
    border-radius: 10px !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    line-height: 1.3 !important;
    padding: 8px 4px !important;
    white-space: pre-line !important;
    border: 1px solid #ffcccc !important;
    background-color: #ffffff !important;
    color: #333333 !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.03) !important;
}

div.stButton > button:hover:not(:disabled) {
    border-color: #ff4b4b !important;
    background-color: #fff0f0 !important;
    color: #ff4b4b !important;
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(255, 75, 75, 0.15) !important;
}

div.stButton > button:disabled {
    border-color: #eee !important;
    background-color: #fafafa !important;
    color: #bbb !important;
    cursor: not-allowed !important;
}
</style>
""", unsafe_allow_html=True)

# アップローダーの配置 (通常位置で描画するが、JSでチャット入力欄に移動させる)
uploaded_file = st.file_uploader("", type=None, label_visibility="collapsed")

# ファイルがアップロードされている場合、プレビューを表示
uploaded_bytes = None
if uploaded_file:
    uploaded_bytes = uploaded_file.read()
    st.markdown(f"""
    <div class="preview-box">
        <span style="font-size: 12px; color: #ff4b4b; font-weight: bold;">📎 ファイル添付中: {uploaded_file.name}</span>
    </div>
    """, unsafe_allow_html=True)

# ---------- 🎯 3択クイズ インタラクティブ回答ボタン ----------
if len(st.session_state.messages) > 0:
    last_msg = st.session_state.messages[-1]
    if last_msg["role"] == "assistant" and "【A】" in last_msg["content"] and "【B】" in last_msg["content"] and "【C】" in last_msg["content"]:
        st.markdown("""
        <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 12px; padding: 10px 14px; margin-top: 12px; margin-bottom: 8px;">
            <span style="font-size: 13px; font-weight: bold; color: #1d4ed8;">🎯 ユッキーからのクイズ！答えを選んでね：</span>
        </div>
        """, unsafe_allow_html=True)
        qc1, qc2, qc3 = st.columns(3)
        with qc1:
            if st.button("🅰️ 選択肢 A", key="quiz_choice_a", use_container_width=True):
                send_message_to_assistant(
                    display_text="私の回答: **A**",
                    ai_prompt="【クイズ解答判定】ユーザーは『選択肢A』を選びました。正解かどうか判定し（ピンポン／ブブーなど）、優しく分かりやすく解説してください。"
                )
        with qc2:
            if st.button("🅱️ 選択肢 B", key="quiz_choice_b", use_container_width=True):
                send_message_to_assistant(
                    display_text="私の回答: **B**",
                    ai_prompt="【クイズ解答判定】ユーザーは『選択肢B』を選びました。正解かどうか判定し（ピンポン／ブブーなど）、優しく分かりやすく解説してください。"
                )
        with qc3:
            if st.button("🅲 選択肢 C", key="quiz_choice_c", use_container_width=True):
                send_message_to_assistant(
                    display_text="私の回答: **C**",
                    ai_prompt="【クイズ解答判定】ユーザーは『選択肢C』を選びました。正解かどうか判定し（ピンポン／ブブーなど）、優しく分かりやすく解説してください。"
                )

# ---------- ヒント＆ギブアップ クイックアクションバー ----------
has_history = len(st.session_state.messages) > 0
if not has_history:
    st.session_state.hint_level = 1

current_level = st.session_state.hint_level

stage_descriptions = {
    1: "💡 ヒント1（着眼点）が使えます",
    2: "🔍 ヒント2（公式・考え方）が解放されました！",
    3: "🔑 ヒント3（最初の一歩）が解放されました！",
    4: "🏳️ ギブアップ（答えと全解説）が解放されました！"
}
stage_sub = stage_descriptions.get(current_level, "")

# タイトル表示とリセット機能
bar_col1, bar_col2 = st.columns([5, 1])
with bar_col1:
    st.markdown(f"""
    <div class="hint-bar-wrapper">
        <div class="hint-bar-title">🎯 段階的ヒント <span class="hint-stage-badge">ヒント {min(current_level, 3)}/3</span></div>
        <div class="hint-bar-sub">{stage_sub if has_history else "質問を送信するとヒント1を利用できます"}</div>
    </div>
    """, unsafe_allow_html=True)
with bar_col2:
    if has_history and current_level > 1:
        if st.button("🔄 最初へ", key="btn_reset_hint", help="ヒントをヒント1に戻します"):
            st.session_state.hint_level = 1
            st.rerun()

# 段階的にボタンを増やす（最初はヒント1のみ、押下でヒント2が解放、順次ギブアップまで解放）
num_cols = min(current_level, 4)
cols = st.columns(num_cols)

# ヒント1（常に表示）
with cols[0]:
    if st.button("💡 ヒント1\n着眼点", key="btn_hint_1", use_container_width=True, disabled=not has_history, help="どこに注目すべきかのポイントを教えてもらいます"):
        st.session_state.hint_level = max(st.session_state.hint_level, 2)
        send_message_to_assistant(
            display_text="💡 **ヒント1（着眼点）** を教えて！",
            ai_prompt="【ヒント1要請】答えや計算式は絶対に言わず、現在取り組んでいる問題の『着眼点（何に注目すべきか、注目ポイント）』だけを優しく教えてください。"
        )

# ヒント2（ヒント1押下後に表示）
if current_level >= 2:
    with cols[1]:
        if st.button("🔍 ヒント2\n公式・考え方", key="btn_hint_2", use_container_width=True, disabled=not has_history, help="使うべき公式や解法の枠組みを教えてもらいます"):
            st.session_state.hint_level = max(st.session_state.hint_level, 3)
            send_message_to_assistant(
                display_text="🔍 **ヒント2（公式・考え方）** を教えて！",
                ai_prompt="【ヒント2要請】答えや計算結果は言わず、この問題で『使うべき公式・考え方のルール・定理』を優しく教えてください。"
            )

# ヒント3（ヒント2押下後に表示）
if current_level >= 3:
    with cols[2]:
        if st.button("🔑 ヒント3\n最初の一歩", key="btn_hint_3", use_container_width=True, disabled=not has_history, help="式の1行目や解法の最初の一歩を教えてもらいます"):
            st.session_state.hint_level = max(st.session_state.hint_level, 4)
            send_message_to_assistant(
                display_text="🔑 **ヒント3（最初の一歩）** を教えて！",
                ai_prompt="【ヒント3要請】最後の答えは言わず、『解法の最初の一歩（式変形の1行目など）』を具体的に教えて、続きを考えられるように優しく導いてください。"
            )

# ギブアップ（ヒント3押下後に表示）
if current_level >= 4:
    with cols[3]:
        if st.button("🏳️ ギブアップ\n答えと全解説", key="btn_give_up", use_container_width=True, disabled=not has_history, help="ここまでの努力を振り返り、完全な正解と詳しい解説を表示します"):
            send_message_to_assistant(
                display_text="🏳️ **ギブアップ！** 答えと全解説を教えて！",
                ai_prompt="【ギブアップ要請】ここまで一生懸命考えた努力を惜しみなく褒めてから、この問題の『完全な正解』と『ステップバイステップのわかりやすい全解説』を優しく教えてください。"
            )

# ---------- 学習サポート アクションバー (解けた！ / 類題ガチャ / 理解度テスト) ----------
if has_history:
    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
    act_col1, act_col2, act_col3 = st.columns([1.2, 1, 1])

    with act_col1:
        if st.button("✨ 自力で解けた！", key="btn_solved_star", use_container_width=True, help="自力正解を報告してスターとスタンプを獲得！"):
            if current_level == 1:
                earned = 3
                eval_msg = "パーフェクト！ノーヒントで自力で解き明かしました！"
            elif current_level == 2:
                earned = 2
                eval_msg = "ナイスひらめき！ヒント1だけで解き切りました！"
            elif current_level == 3:
                earned = 1
                eval_msg = "素晴らしい粘り強さ！ヒントを活用して解き切りました！"
            else:
                earned = 1
                eval_msg = "完走おめでとう！最後まで諦めずに解き切りました！"

            st.session_state.stars += earned
            st.session_state.stamps += 1
            save_user_data(st.session_state.loaded_user_id)
            st.balloons()
            send_message_to_assistant(
                display_text=f"✨ **自力で解けたよ！（⭐×{earned}個 獲得！）**",
                ai_prompt=f"【自力正解の称賛要請】ユーザーが見事に問題を解き終えました（{eval_msg}）。大喜びでたくさん褒めて、努力を称賛し、自信をつけさせてあげてください！"
            )

    with act_col2:
        if st.button("🎲 類題ガチャ", key="btn_toggle_gacha", use_container_width=True, help="似た問題を出題して復習します"):
            st.session_state.show_gacha = not st.session_state.show_gacha
            st.rerun()

    with act_col3:
        if st.button("🎯 理解度テスト", key="btn_req_quiz", use_container_width=True, help="この問題に関する3択ミニテストを出題してもらいます"):
            send_message_to_assistant(
                display_text="🎯 **理解度テストを出題して！**",
                ai_prompt="【理解度クイズ出題要請】直前の問題の要点や重要公式に関する「3択クイズ」を1問作成してください。出力は必ず以下の書式を含めてください：\n【問題】（ここに問題文）\n【A】（選択肢1）\n【B】（選択肢2）\n【C】（選択肢3）"
            )

    if st.session_state.show_gacha:
        st.markdown("""
        <div style="background: #fffbeb; border: 1px dashed #f59e0b; border-radius: 12px; padding: 8px 12px; margin-top: 8px; margin-bottom: 8px;">
            <span style="font-size: 13px; font-weight: bold; color: #b45309;">🎲 類題ガチャ：挑戦する難易度を選んでね！</span>
        </div>
        """, unsafe_allow_html=True)
        g_c1, g_c2, g_c3 = st.columns(3)
        with g_c1:
            if st.button("🟢 少しカンタン", key="gacha_easy", use_container_width=True):
                st.session_state.hint_level = 1
                st.session_state.show_gacha = False
                send_message_to_assistant(
                    display_text="🎲 **【類題ガチャ】少しカンタンな問題** をお願い！",
                    ai_prompt="【類題出題要請】難易度:『少しカンタン』。直前の問題と同じ解法パターン・公式を使い、計算がよりシンプルな類題を1問出題してください。答えや解説は書かず、問題文だけを出して挑戦を促してください。"
                )
        with g_c2:
            if st.button("🟡 同じレベル", key="gacha_mid", use_container_width=True):
                st.session_state.hint_level = 1
                st.session_state.show_gacha = False
                send_message_to_assistant(
                    display_text="🎲 **【類題ガチャ】同じレベルの問題** をお願い！",
                    ai_prompt="【類題出題要請】難易度:『同じレベル』。直前の問題と同じ解法パターン・公式を使い、数値やシチュエーションを変えた類題を1問出題してください。答えや解説は書かず、問題文だけを出して挑戦を促してください。"
                )
        with g_c3:
            if st.button("🔴 チャレンジ応用", key="gacha_hard", use_container_width=True):
                st.session_state.hint_level = 1
                st.session_state.show_gacha = False
                send_message_to_assistant(
                    display_text="🎲 **【類題ガチャ】チャレンジ応用問題** をお願い！",
                    ai_prompt="【類題出題要請】難易度:『チャレンジ応用』。直前の問題の考え方を応用する、少しひねりのある発展類題を1問出題してください。答えや解説は書かず、問題文だけを出して挑戦を促してください。"
                )

# ---------- テキストチャット入力 ----------
if prompt := st.chat_input("質問を入力してください…"):
    send_message_to_assistant(
        display_text=prompt,
        ai_prompt=prompt,
        attach_bytes=uploaded_bytes,
        attach_file=uploaded_file
    )

# DOM操作でアップローダーとマイクボタンを stChatInput の内側に移動・追加するJSスクリプト
components.html("""
<script>
    // 状態を parent ウィンドウに保存して再実行後も維持する
    if (typeof window.parent.conversationMode === 'undefined') {
        window.parent.conversationMode = false;
    }
    if (typeof window.parent.isListening === 'undefined') {
        window.parent.isListening = false;
    }

    function moveUploader() {
        const uploader = window.parent.document.querySelector('div[data-testid="stFileUploader"]');
        const chatInput = window.parent.document.querySelector('div[data-testid="stChatInput"]');
        if (uploader && chatInput && uploader.parentElement !== chatInput) {
            chatInput.insertBefore(uploader, chatInput.firstChild);
        }
    }

    function addMicButton() {
        const chatInput = window.parent.document.querySelector('div[data-testid="stChatInput"]');
        if (!chatInput) return;
        
        let micBtn = window.parent.document.getElementById('yukki-mic-btn');
        if (!micBtn) {
            micBtn = window.parent.document.createElement('button');
            micBtn.id = 'yukki-mic-btn';
            micBtn.innerHTML = '🎤';
            micBtn.style.position = 'absolute';
            micBtn.style.right = '58px'; /* 送信ボタンの左側 */
            micBtn.style.top = '50%';
            micBtn.style.transform = 'translateY(-50%)';
            micBtn.style.background = 'transparent';
            micBtn.style.border = 'none';
            micBtn.style.fontSize = '18px';
            micBtn.style.cursor = 'pointer';
            micBtn.style.zIndex = '9999';
            micBtn.style.padding = '6px';
            micBtn.style.borderRadius = '50%';
            micBtn.style.display = 'flex';
            micBtn.style.alignItems = 'center';
            micBtn.style.justifyContent = 'center';
            micBtn.style.transition = 'all 0.2s';
            
            micBtn.addEventListener('click', toggleConversationMode);
            chatInput.appendChild(micBtn);
        }
        
        updateMicButtonStyle();
    }

    function updateMicButtonStyle() {
        const micBtn = window.parent.document.getElementById('yukki-mic-btn');
        if (!micBtn) return;
        
        if (window.parent.isListening) {
            micBtn.innerHTML = '🔴';
            micBtn.style.backgroundColor = '#ffcccc';
            micBtn.style.boxShadow = '0 0 8px #ff4b4b';
        } else if (window.parent.conversationMode) {
            micBtn.innerHTML = '🎤';
            micBtn.style.backgroundColor = '#e0f7fa';
            micBtn.style.boxShadow = '0 0 8px #00bcd4';
        } else {
            micBtn.innerHTML = '🎤';
            micBtn.style.backgroundColor = 'transparent';
            micBtn.style.boxShadow = 'none';
        }
    }

    // 音声認識の設定 (ブラウザ標準)
    const SpeechRecognition = window.parent.SpeechRecognition || window.parent.webkitSpeechRecognition;
    if (SpeechRecognition && !window.parent.recognition) {
        const rec = new SpeechRecognition();
        rec.lang = 'ja-JP';
        rec.continuous = false;
        rec.interimResults = false;
        
        rec.onstart = () => {
            window.parent.isListening = true;
            updateMicButtonStyle();
        };
        
        rec.onend = () => {
            window.parent.isListening = false;
            updateMicButtonStyle();
            // 話し終わった後に会話モードがONで、かつ喋っていない状態であれば次の聞き取り待機に入ることはTTS側で制御
        };
        
        rec.onresult = (event) => {
            const text = event.results[0][0].transcript;
            const textarea = window.parent.document.querySelector('div[data-testid="stChatInput"] textarea');
            if (textarea && text) {
                // Reactの状態を同期させるためにネイティブセッターを使用
                const valueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                valueSetter.call(textarea, text);
                textarea.dispatchEvent(new Event('input', { bubbles: true }));
                
                // 少しディレイを挟んで自動送信ボタンをクリック
                setTimeout(() => {
                    const sendBtn = window.parent.document.querySelector('div[data-testid="stChatInput"] button[data-testid="stChatInputSubmitButton"]');
                    if (sendBtn) {
                        sendBtn.click();
                    }
                }, 300);
            }
        };
        
        rec.onerror = (e) => {
            console.error("Speech Recognition error:", e);
            window.parent.isListening = false;
            updateMicButtonStyle();
        };
        
        window.parent.recognition = rec;
    }

    // グローバルに呼び出せる関数としてparentに定義
    window.parent.startListening = function() {
        if (window.parent.recognition && !window.parent.isListening) {
            window.parent.speechSynthesis.cancel();
            window.parent.recognition.start();
        }
    };

    window.parent.stopListening = function() {
        if (window.parent.recognition && window.parent.isListening) {
            window.parent.recognition.stop();
        }
    };

    function toggleConversationMode() {
        if (window.parent.conversationMode) {
            window.parent.conversationMode = false;
            window.parent.stopListening();
            window.parent.speechSynthesis.cancel();
        } else {
            window.parent.conversationMode = true;
            window.parent.startListening();
        }
        updateMicButtonStyle();
    }

    // 定期的に状態を確認・適用するループ
    setInterval(() => {
        moveUploader();
        addMicButton();
    }, 150);
</script>
""", height=0, width=0)