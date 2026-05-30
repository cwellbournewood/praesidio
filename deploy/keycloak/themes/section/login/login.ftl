<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('username','password') displayInfo=realm.password && realm.registrationAllowed && !registrationDisabled??; section>
  <#if section = "form">
    <#if realm.password>
      <form id="kc-form-login" class="form" onsubmit="login.disabled = true; return true;" action="${url.loginAction}" method="post" novalidate>
        <#if !usernameHidden??>
          <label class="field">
            <span class="field__label">${msg("usernameOrEmail")}</span>
            <input
              tabindex="1"
              id="username"
              class="field__input"
              name="username"
              value="${(login.username!'')}"
              type="text"
              autofocus
              autocomplete="username"
              spellcheck="false"
              aria-invalid="<#if messagesPerField.existsError('username','password')>true</#if>"
            />
            <#if messagesPerField.existsError('username','password')>
              <span id="input-error" class="field__error" aria-live="polite">
                ${kcSanitize(messagesPerField.getFirstError('username','password'))?no_esc}
              </span>
            </#if>
          </label>
        </#if>

        <label class="field">
          <span class="field__label">${msg("password")}</span>
          <input
            tabindex="2"
            id="password"
            class="field__input field__input--mono"
            name="password"
            type="password"
            autocomplete="current-password"
            aria-invalid="<#if messagesPerField.existsError('username','password')>true</#if>"
          />
        </label>

        <div class="form__row">
          <#if realm.rememberMe && !usernameHidden??>
            <label class="checkbox">
              <input tabindex="3" id="rememberMe" name="rememberMe" type="checkbox" <#if login.rememberMe??>checked</#if>>
              <span class="checkbox__box" aria-hidden="true"></span>
              <span class="checkbox__label">${msg("rememberMe")}</span>
            </label>
          <#else>
            <span></span>
          </#if>
          <#if realm.resetPasswordAllowed>
            <a tabindex="5" class="link" href="${url.loginResetCredentialsUrl}">${msg("doForgotPassword")}</a>
          </#if>
        </div>

        <input type="hidden" id="id-hidden-input" name="credentialId" <#if auth.selectedCredential?has_content>value="${auth.selectedCredential}"</#if>/>

        <button
          tabindex="4"
          class="btn btn--primary"
          name="login"
          id="kc-login"
          type="submit"
        >
          <span class="sig sig--allow" aria-hidden="true"></span>
          <span>${msg("doLogIn")}</span>
          <span class="btn__arrow" aria-hidden="true">→</span>
        </button>
      </form>
    </#if>

    <#if realm.password && social.providers??>
      <div class="divider"><span>or</span></div>
      <ul class="socials">
        <#list social.providers as p>
          <li>
            <a class="btn btn--ghost" href="${p.loginUrl}" id="social-${p.alias}">
              <span class="sig sig--warn" aria-hidden="true"></span>
              <span>${p.displayName!p.alias}</span>
            </a>
          </li>
        </#list>
      </ul>
    </#if>
  </#if>
</@layout.registrationLayout>
