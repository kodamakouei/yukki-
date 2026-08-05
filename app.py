import streamlit as st
from google import genai
import base64
import json
import requests
import streamlit.components.v1 as components
import os
import time
from google.genai.types import Part

# =========================================
#  システムプロンプト
# =========================================
SYSTEM_PROMPT = """
あなたは教育的な目的を持つ AI アシスタントです。
ユーザーの質問に対して以下のルールに従ってできるだけかみ砕いてわかりやすく応答してく
ださい。
1⃣知識・定義直接答えます。
2⃣思考・計算問題答えは教えず、解法のヒントのみを示します。
3⃣途中式正誤を判定し、優しく導きます。
4⃣専門用語ステップごとに区切り、専門用語について知っているか確認します。知らなかっ
た場合は、小学生にもわかるように、図や擬音などの表現、例となる面白い文を積極的に使っ
てその場で説明します。
5⃣説明は砕けた会話口調でお願いします。
6⃣いきなりステップを全部出さないでください。「ここで、～～について知っていますか？」
のところでいったん表示するのをやめてください。
7⃣専門用語や途中の過程の分からない部分について説明されたときは、できるだけ詳しく説明
してください。だからと言ってその説明を聞いている人に読むのを飽きさせてしまうような説
明はやめてください。

"""

# =========================================
# APIキー読み込みと画像Base64変換関数
# =========================================
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = ""
    

def get_base64_image(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as f:
            data = f.read()
            return base64.b64encode(data).decode("utf-8")
    return ""

# 画像の準備
IMG_ICON_B64 = get_base64_image("yukki-icon.jpg")
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

# 📸 サイドバー
with st.sidebar:
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

# =========================================
# メイン画面 UI
# =========================================
st.title("🎀 疑似教師AIユッキー")
st.caption("ユッキーが解説してくれます！入力欄左端の「＋」から画像を添付して質問できます。")

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
</style>
""", unsafe_allow_html=True)

# アップローダーの配置 (通常位置で描画するが、JSでチャット入力欄に移動させる)
uploaded_image = st.file_uploader("", type=["jpg", "jpeg", "png"], label_visibility="collapsed")

# 画像がアップロードされている場合、プレビューを表示
uploaded_bytes = None
if uploaded_image:
    uploaded_bytes = uploaded_image.read()
    st.markdown(f"""
    <div class="preview-box">
        <span style="font-size: 12px; color: #ff4b4b; font-weight: bold;">📎 画像添付中: {uploaded_image.name}</span>
    </div>
    """, unsafe_allow_html=True)

# ---------- テキストチャット入力 ----------
if prompt := st.chat_input("質問を入力してください…"):
    st.session_state.messages.append({"role": "user", "content": prompt})

    contents_to_send = [prompt]
    
    if uploaded_image and uploaded_bytes:
        try:
            image_part = Part.from_bytes(
                data=uploaded_bytes,
                mime_type=uploaded_image.type
            )
            contents_to_send.append(image_part)
        except Exception as e:
            print(f"画像データの変換エラー: {e}")
            
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