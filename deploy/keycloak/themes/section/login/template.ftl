<#macro registrationLayout bodyClass="" displayInfo=false displayMessage=true displayRequiredFields=false showAnotherWayIfPresent=true>
<!DOCTYPE html>
<html lang="${(locale.currentLanguageTag)!'en'}" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>${msg("loginAccountTitle")} · ${msg("brand.name")}</title>
  <link rel="icon" href="${url.resourcesPath}/img/favicon.svg" type="image/svg+xml">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital,wght@0,400;1,400&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500&display=swap">
  <#if properties.styles?has_content>
    <#list properties.styles?split(' ') as style>
      <link rel="stylesheet" href="${url.resourcesPath}/${style}">
    </#list>
  </#if>
</head>
<body class="section-login ${bodyClass}">
  <header class="topbar" role="banner">
    <div class="topbar__left">
      <span class="kbd-section">§</span>
      <span class="brand-word">${msg("brand.name")}</span>
      <span class="brand-tagline">${msg("brand.tagline")}</span>
    </div>
    <div class="topbar__right">
      <#if realm.internationalizationEnabled?? && realm.internationalizationEnabled && (locale.supported)?? && locale.supported?size gt 1>
        <div class="locale">
          <#list locale.supported as l>
            <#if l.languageTag == locale.currentLanguageTag>
              <span class="locale__current">${l.languageTag?upper_case}</span>
            <#else>
              <a href="${l.url}" class="locale__alt">${l.languageTag?upper_case}</a>
            </#if>
          </#list>
        </div>
      </#if>
      <span class="chip chip--mode">SSO</span>
    </div>
  </header>

  <main class="grid">
    <aside class="aside" aria-hidden="true">
      <div class="aside__eyebrow">CONTROL PLANE · IDENTITY</div>
      <h2 class="aside__title">
        <em>Sign in</em><br>
        to your<br>
        instrument.
      </h2>
      <p class="aside__lede">
        Section mediates every prompt, response and tool call between your
        people and the models they use. Single sign-on resolves who is
        asking — so policy can resolve what they are allowed to ask for.
      </p>
      <dl class="aside__facts">
        <div><dt>i.</dt><dd>SSO via your IdP. No new passwords.</dd></div>
        <div><dt>ii.</dt><dd>Group → role mapping is auditable.</dd></div>
        <div><dt>iii.</dt><dd>Every sign-in is hash-chained.</dd></div>
      </dl>
    </aside>

    <section class="card" aria-labelledby="login-title">
      <div class="card__eyebrow">
        <span class="sig sig--allow" aria-hidden="true"></span>
        <span>i. AUTHENTICATE</span>
      </div>

      <h1 id="login-title" class="card__title">
        <#if displayMessage && message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
          ${msg("errorTitle")}
        <#else>
          ${msg("loginAccountTitle")}
        </#if>
      </h1>

      <#if realm.displayNameHtml?? && realm.displayNameHtml?has_content>
        <p class="card__sub">${kcSanitize(realm.displayNameHtml)?no_esc}</p>
      <#else>
        <p class="card__sub">Sign in with your corporate identity to continue to the console.</p>
      </#if>

      <#-- Error / info banner -->
      <#if displayMessage && message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
        <div class="alert alert--${message.type}" role="alert">
          <span class="alert__rule"></span>
          <span class="alert__text">${kcSanitize(message.summary)?no_esc}</span>
        </div>
      </#if>

      <#nested "form">

      <#if displayInfo>
        <div class="card__info">
          <#nested "info">
        </div>
      </#if>
    </section>

    <footer class="marginalia" role="contentinfo">
      <span class="sig sig--allow" aria-hidden="true"></span>
      <span class="marginalia__primary">${msg("brand.footnote")}</span>
      <span class="marginalia__sep">·</span>
      <span class="marginalia__alt">${realm.name}</span>
    </footer>
  </main>

  <div class="statusbar" role="status">
    <span><span class="sig sig--allow" aria-hidden="true"></span> KEYCLOAK · READY</span>
    <span>REALM <code>${realm.name}</code></span>
    <span>${msg("brand.name")} v0.1.0</span>
  </div>
</body>
</html>
</#macro>
