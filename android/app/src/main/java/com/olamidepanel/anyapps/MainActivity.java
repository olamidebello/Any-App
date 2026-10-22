package com.olamidepanel.anyapps;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

/** Thin Android client. Payment pages open in the system browser, never in an embedded card form. */
public class MainActivity extends Activity {
    private WebView web;
    private static final String HOST = "anyapp.olamidepanel.com";
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(23,19,52));
        LinearLayout layout = new LinearLayout(this); layout.setOrientation(LinearLayout.VERTICAL);
        ProgressBar progress = new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);
        layout.addView(progress,new LinearLayout.LayoutParams(-1,8));
        web = new WebView(this); layout.addView(web,new LinearLayout.LayoutParams(-1,-1)); setContentView(layout);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(false);
        web.getSettings().setMixedContentMode(android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);
        web.setWebChromeClient(new WebChromeClient(){@Override public void onProgressChanged(WebView view,int value){progress.setProgress(value);progress.setVisibility(value==100?android.view.View.GONE:android.view.View.VISIBLE);}});
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest req){
                Uri uri=req.getUrl();
                if("https".equals(uri.getScheme()) && HOST.equals(uri.getHost())) return false;
                if(req.isForMainFrame() && ("https".equals(uri.getScheme()) || "mailto".equals(uri.getScheme()))) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW,uri)); } catch(Exception ignored) { }
                }
                return true;
            }
            @Override public void onReceivedError(WebView view,WebResourceRequest req,android.webkit.WebResourceError error){
                if(req.isForMainFrame()){
                    TextView notice=new TextView(MainActivity.this);notice.setText("AnyApps could not connect. Check your connection, then reopen the app. Your saved projects are safe on the server.");notice.setPadding(40,80,40,40);setContentView(notice);
                }
            }
        });
        web.setDownloadListener((url,userAgent,contentDisposition,mimeType,contentLength)->{
            Uri uri=Uri.parse(url);
            if(!"https".equals(uri.getScheme()) || !HOST.equals(uri.getHost())) return;
            try {
                DownloadManager.Request download=new DownloadManager.Request(uri);
                String cookie=CookieManager.getInstance().getCookie(url);
                if(cookie!=null) download.addRequestHeader("Cookie",cookie);
                download.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                download.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS,mimeType!=null&&mimeType.contains("zip")?"AnyApps-project.zip":"AnyApps.apk");
                ((DownloadManager)getSystemService(DOWNLOAD_SERVICE)).enqueue(download);
            } catch(Exception ignored) { }
        });
        if(state!=null) web.restoreState(state); else web.loadUrl("https://"+HOST+"/");
    }
    @Override public void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);web.saveState(out);}
    @Override public void onBackPressed(){if(web.canGoBack())web.goBack();else super.onBackPressed();}
    @Override public void onDestroy(){web.destroy();super.onDestroy();}
}
