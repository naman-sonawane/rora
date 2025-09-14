// VapiLiveNarration.cs
// Attach this to a GameObject in your scene. Call StartNarration() to begin.

using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using TMPro; // optional for on-screen logs
using Newtonsoft.Json.Linq;

public class VapiLiveNarration : MonoBehaviour
{
    [Header("Backend")]
    public string BackendBaseUrl = "http://localhost:8000";

    [Header("Server-side video path (dev only)")]
    public string ServerFilePath = "/mnt/data/sample.mp4";
    public string UserName = "Guest";

    [Header("UI (optional)")]
    public TextMeshProUGUI StatusText;

    private string sessionId;
    private AudioSource audioSource;

    void Awake()
    {
        audioSource = gameObject.AddComponent<AudioSource>();
        audioSource.playOnAwake = false;
        audioSource.loop = true;
        audioSource.spatialBlend = 0f;
    }

    public void StartNarration()
    {
        Log("Starting");
        StartCoroutine(StartNarrationCo());
    }

    IEnumerator StartNarrationCo()
    {
        Log("Starting narration…");

        var payload = new JObject
        {
            ["file_path"] = ServerFilePath,
            ["user_name"] = UserName,
            ["style"] = "warm, concise, present tense"
        };

        using var req = new UnityWebRequest($"{BackendBaseUrl}/start-narration", "POST");
        byte[] body = Encoding.UTF8.GetBytes(payload.ToString());
        req.uploadHandler = new UploadHandlerRaw(body);
        req.downloadHandler = new DownloadHandlerBuffer();
        req.SetRequestHeader("Content-Type", "application/json");

        yield return req.SendWebRequest();

        if (req.result != UnityWebRequest.Result.Success)
        {
            LogError($"start-narration error: {req.error} :: {req.downloadHandler.text}");
            yield break;
        }

        var json = JObject.Parse(req.downloadHandler.text);
        sessionId = json.Value<string>("session_id");
        var vapiSessionRaw = json["vapi_session_raw"] as JObject;
        Log($"Got session: {sessionId}");

        // ===== CONNECT TO VAPI WEBRTC =====
        // Your Vapi org exposes a signaling endpoint / credentials with the session.
        // Depending on your WebRTC plugin, you'll:
        // 1) Create a PeerConnection
        // 2) Exchange SDP/ICE with Vapi (sessionId + signaling URL/token)
        // 3) On remote audio track, route to AudioSource and Play()

        // Example call (pseudo; replace with your chosen plugin):
        // yield return StartCoroutine(ConnectToVapiWebRTC(sessionId, vapiSessionRaw));

        Log("If your assistant has a firstMessage, it will start speaking as soon as WebRTC connects.");
    }

    // Optional: forward a message mid-experience (e.g., player enters a room)
    public void SendFollowup(string text)
    {
        if (string.IsNullOrEmpty(sessionId))
        {
            LogError("No session started yet.");
            return;
        }
        StartCoroutine(SendMessageCo(text));
    }

    IEnumerator SendMessageCo(string text)
    {
        WWWForm form = new WWWForm();
        form.AddField("session_id", sessionId);
        form.AddField("text", text);

        using var req = UnityWebRequest.Post($"{BackendBaseUrl}/send-message", form);
        yield return req.SendWebRequest();

        if (req.result != UnityWebRequest.Result.Success)
        {
            LogError($"send-message error: {req.error} :: {req.downloadHandler.text}");
            yield break;
        }
        Log($"Sent: {text}");
    }

    // ========== helpers ==========
    void Log(string msg)
    {
        Debug.Log(msg);
        if (StatusText) StatusText.text = msg;
    }

    void LogError(string msg)
    {
        Debug.LogError(msg);
        if (StatusText) StatusText.text = $"<color=red>{msg}</color>";
    }
}