# Bootstrapping the JetBrains plugin build

`gradle-wrapper.jar` is intentionally **not committed** to the repo (binary
artifact policy). One of the following must be done before the first build
on a fresh checkout:

## Option A — you have Gradle 8.5+ installed system-wide

```bash
cd clients/jetbrains
gradle wrapper --gradle-version 8.5 --distribution-type bin
```

This populates `gradle/wrapper/gradle-wrapper.jar` and `gradlew` is then
self-sufficient.

## Option B — you don't have Gradle locally

Use the GitHub Actions build (`.github/workflows/edge.yml` → `jetbrains`
job) which bootstraps the wrapper automatically via the
`gradle/actions/setup-gradle@v3` action.

## Option C — fetch the verified wrapper jar from upstream

```bash
cd clients/jetbrains/gradle/wrapper
curl -fLO https://github.com/gradle/gradle/raw/v8.5.0/gradle/wrapper/gradle-wrapper.jar
echo "<expected sha256>  gradle-wrapper.jar" | sha256sum -c -
```

The expected sha256 is published in
`gradle/wrapper/gradle-wrapper.properties` via `distributionSha256Sum=`.

## After bootstrap

```bash
./gradlew test         # run unit tests
./gradlew buildPlugin  # produce build/distributions/praesidio-jetbrains-*.zip
./gradlew ktlintCheck  # lint
```
