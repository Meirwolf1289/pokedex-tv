package tv.hush.pokedex;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.media.tv.TvContract;
import android.media.tv.TvInputInfo;
import android.media.tv.TvInputManager;
import android.provider.Settings;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;

/** A full-screen WebView around index.html; the page talks to the TV through the Hush bridge (window.Hush). */
public class MainActivity extends Activity {
    private WebView web;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);                    // the app order, the TMDB key, the mute switch
        s.setMediaPlaybackRequiresUserGesture(false);    // the aerials start on their own
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW); // Apple serves the aerials over plain http
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        web.setBackgroundColor(0xFF000000);
        web.addJavascriptInterface(new Bridge(), "Hush");
        web.loadUrl("file:///android_asset/index.html");
        setContentView(web);
        hideSystemUi();
    }

    private void hideSystemUi() {
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                | View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION);
    }

    @Override
    public void onBackPressed() {
        // The page handles Back itself (close a sheet, go to the first app); a home screen never exits on Back.
        web.evaluateJavascript("document.dispatchEvent(new KeyboardEvent('keydown',{keyCode:27,which:27,bubbles:true}))", null);
    }

    @Override
    public boolean onKeyDown(int code, KeyEvent e) {
        if (code == KeyEvent.KEYCODE_BACK) { onBackPressed(); return true; }
        return super.onKeyDown(code, e);
    }

    final class Bridge {
        /** Opens the first of these packages that is installed; true when one started. */
        @JavascriptInterface
        public boolean launch(String packages) {
            PackageManager pm = getPackageManager();
            for (String p : packages.split(",")) {
                p = p.trim();
                if (p.isEmpty()) continue;
                Intent i = pm.getLeanbackLaunchIntentForPackage(p);
                if (i == null) i = pm.getLaunchIntentForPackage(p);
                if (i == null) continue;
                i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                try { startActivity(i); return true; } catch (Exception ignored) {}
            }
            return false;
        }

        /** The TV's own settings screen. */
        @JavascriptInterface
        public boolean openSettings() {
            try { startActivity(new Intent(Settings.ACTION_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); return true; }
            catch (Exception e) { return false; }
        }

        /** The n-th HDMI port (1-based), through Android TV's passthrough input; false where no app answers it. */
        @JavascriptInterface
        public boolean input(int n) {
            TvInputManager tim = (TvInputManager) getSystemService(TV_INPUT_SERVICE);
            if (tim == null) return false;
            List<TvInputInfo> ports = new ArrayList<>();
            try {
                for (TvInputInfo info : tim.getTvInputList())
                    if (info.getType() == TvInputInfo.TYPE_HDMI && info.getParentId() == null) ports.add(info);
            } catch (RuntimeException e) { return false; }
            Collections.sort(ports, (a, b) -> a.getId().compareTo(b.getId()));
            if (n < 1 || n > ports.size()) return false;
            Intent i = new Intent(Intent.ACTION_VIEW, TvContract.buildChannelUriForPassthroughInput(ports.get(n - 1).getId()));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            try { startActivity(i); return true; } catch (Exception e) { return false; }
        }
    }
}
