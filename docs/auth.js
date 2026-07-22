/* ══════════════════════════════════════════════════════════
   تسجيل الدخول بحساب جوجل (جيميل حقيقي) عبر Firebase
   ──────────────────────────────────────────────────────────
   ضع بيانات مشروعك في FIREBASE_CONFIG أدناه.
   ما دامت القيم فارغة، يعمل الموقع بدون تسجيل دخول كما هو الآن.
   ══════════════════════════════════════════════════════════ */

const FIREBASE_CONFIG = {
  apiKey: "",
  authDomain: "",
  projectId: "",
  appId: "",
};

/* إن أردت قصر الدخول على إيميلات محددة، اكتبها هنا.
   اتركها فارغة ليدخل أي شخص بحساب جوجل. */
const ALLOWED_EMAILS = [];

/* ══════════════════════════════════════════════════════════ */

const ready = FIREBASE_CONFIG.apiKey && FIREBASE_CONFIG.authDomain;

/* شاشة الدخول — تُبنى بالكود حتى لا تظهر أبداً إن كان الدخول معطّلاً */
function gateHTML() {
  return `
  <div id="gate" style="
      position:fixed;inset:0;z-index:200;background:#080c15;
      display:grid;place-items:center;padding:24px;
      font-family:Tajawal,Tahoma,sans-serif;color:#eef2f9">
    <div style="max-width:360px;width:100%;text-align:center">
      <h2 style="font-size:22px;font-weight:800;margin-bottom:10px">فرص السوق الأمريكي</h2>
      <p style="font-size:13.5px;color:#8b97ae;line-height:1.8;margin-bottom:26px">
        سجّل الدخول بحساب جوجل لعرض الإشارات
      </p>

      <button id="gBtn" style="
          width:100%;display:flex;align-items:center;justify-content:center;gap:11px;
          background:#fff;color:#1f1f1f;border:none;border-radius:12px;
          padding:13px 18px;font-size:14.5px;font-weight:700;
          font-family:inherit;cursor:pointer;transition:.15s">
        <svg width="19" height="19" viewBox="0 0 48 48" aria-hidden="true">
          <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.9 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.2C12.4 13.700 17.7 9.5 24 9.5z"/>
          <path fill="#4285F4" d="M46.1 24.6c0-1.6-.1-2.8-.4-4.1H24v7.4h12.7c-.3 2.1-1.6 5.3-4.7 7.4l7.3 5.6c4.3-4 6.8-9.9 6.8-16.3z"/>
          <path fill="#FBBC05" d="M10.5 28.6c-.5-1.4-.8-2.9-.8-4.6s.3-3.2.8-4.6l-7.9-6.2C1 16.5 0 20.1 0 24s1 7.5 2.6 10.8l7.9-6.2z"/>
          <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.3-5.6c-2 1.4-4.6 2.4-8.6 2.4-6.3 0-11.6-4.2-13.5-9.9l-7.9 6.2C6.5 42.6 14.6 48 24 48z"/>
        </svg>
        <span>الدخول بحساب جوجل</span>
      </button>

      <p id="gMsg" style="font-size:12.5px;color:#fb5573;margin-top:16px;line-height:1.8;min-height:20px"></p>
      <p style="font-size:11px;color:#5a6478;margin-top:22px;line-height:1.8">
        نستخدم حسابك للتعرّف عليك فقط — لا نطّلع على كلمة سرك ولا على بريدك.
      </p>
    </div>
  </div>`;
}

/* شارة المستخدم أعلى الصفحة */
function badge(user) {
  const el = document.createElement("div");
  el.style.cssText =
    "display:flex;align-items:center;gap:9px;margin-top:14px;font-size:12px;color:#8b97ae";
  el.innerHTML = `
    ${user.photoURL ? `<img src="${user.photoURL}" alt="" width="24" height="24"
       style="border-radius:50%;flex:none" referrerpolicy="no-referrer">` : ""}
    <span>${user.displayName || user.email}</span>
    <button id="outBtn" style="background:none;border:none;color:#5b8dff;
      font-family:inherit;font-size:12px;font-weight:600;cursor:pointer;padding:0">خروج</button>`;
  document.querySelector("header").appendChild(el);
  return el;
}

async function start() {
  if (!ready) return; // الدخول غير مفعّل — الموقع يعمل كالمعتاد

  // نخفي المحتوى فوراً حتى لا يظهر لجزء من الثانية قبل التحقق
  document.body.insertAdjacentHTML("beforeend", gateHTML());
  const gate = document.getElementById("gate");
  const msg = document.getElementById("gMsg");

  const { initializeApp } = await import(
    "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js");
  const { getAuth, GoogleAuthProvider, signInWithPopup, signInWithRedirect,
          onAuthStateChanged, signOut } = await import(
    "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js");

  const auth = getAuth(initializeApp(FIREBASE_CONFIG));
  const provider = new GoogleAuthProvider();

  document.getElementById("gBtn").onclick = async () => {
    msg.textContent = "";
    try {
      await signInWithPopup(auth, provider);
    } catch (e) {
      // المتصفحات على الجوال تحجب النوافذ المنبثقة أحياناً
      if (String(e.code).includes("popup")) return signInWithRedirect(auth, provider);
      msg.textContent = "تعذّر تسجيل الدخول. حاول مرة أخرى.";
    }
  };

  onAuthStateChanged(auth, (user) => {
    if (!user) { gate.style.display = "grid"; return; }

    if (ALLOWED_EMAILS.length && !ALLOWED_EMAILS.includes(user.email)) {
      msg.textContent = "هذا الحساب غير مصرّح له بالدخول.";
      signOut(auth);
      return;
    }

    gate.style.display = "none";
    if (!document.getElementById("outBtn")) {
      badge(user).querySelector("#outBtn").onclick = () => signOut(auth);
    }
  });
}

start();
