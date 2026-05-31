{{/*
Expand the name of the chart.
*/}}
{{- define "section.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "section.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Chart name + version label.
*/}}
{{- define "section.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels applied to every object.
*/}}
{{- define "section.labels" -}}
helm.sh/chart: {{ include "section.chart" . }}
{{ include "section.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: section
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/*
Selector labels (stable, never include version-bound values).
*/}}
{{- define "section.selectorLabels" -}}
app.kubernetes.io/name: {{ include "section.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Per-component labels (gateway / ui / postgres / redis).
Usage: include "section.componentLabels" (dict "ctx" . "component" "gateway")
*/}}
{{- define "section.componentLabels" -}}
{{- $ctx := .ctx -}}
{{ include "section.labels" $ctx }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "section.componentSelectorLabels" -}}
{{- $ctx := .ctx -}}
{{ include "section.selectorLabels" $ctx }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/*
Component fullname (release-name-component).
*/}}
{{- define "section.componentName" -}}
{{- printf "%s-%s" (include "section.fullname" .ctx) .component | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common annotations.
*/}}
{{- define "section.annotations" -}}
{{- with .Values.commonAnnotations }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/*
ServiceAccount name.
*/}}
{{- define "section.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "section.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Image reference. Usage: include "section.image" (dict "img" .Values.image.gateway "ctx" .)
*/}}
{{- define "section.image" -}}
{{- $img := .img -}}
{{- $tag := default .ctx.Chart.AppVersion $img.tag -}}
{{- printf "%s:%s" $img.repository $tag -}}
{{- end -}}

{{/*
Postgres host: embedded or external (DSN parsed by gateway).
Returned only when embedded is true; otherwise the DSN secret/env wins.
*/}}
{{- define "section.postgresHost" -}}
{{- if .Values.postgres.embedded -}}
{{- printf "%s-postgres" (include "section.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
Redis host (embedded).
*/}}
{{- define "section.redisHost" -}}
{{- if .Values.redis.embedded -}}
{{- printf "%s-redis" (include "section.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
DATABASE_URL value: embedded vs external.
*/}}
{{- define "section.databaseUrl" -}}
{{- if .Values.postgres.embedded -}}
{{- printf "postgresql+asyncpg://section:section@%s-postgres:5432/section" (include "section.fullname" .) -}}
{{- else -}}
{{- .Values.postgres.externalDSN -}}
{{- end -}}
{{- end -}}

{{/*
REDIS_URL value: embedded vs external.
*/}}
{{- define "section.redisUrl" -}}
{{- if .Values.redis.embedded -}}
{{- printf "redis://%s-redis:6379/0" (include "section.fullname" .) -}}
{{- else -}}
{{- .Values.redis.externalURL -}}
{{- end -}}
{{- end -}}

{{/*
Secret name for the gateway. Centralised so deployment + externalsecret agree.
*/}}
{{- define "section.gatewaySecretName" -}}
{{- printf "%s-gateway" (include "section.fullname" .) -}}
{{- end -}}

{{/*
ConfigMap name for the policy bundle.
*/}}
{{- define "section.policyConfigMapName" -}}
{{- printf "%s-policies" (include "section.fullname" .) -}}
{{- end -}}
