/*
 * ==========================================================================
 *  AmplifierSetupBackend.h — Settings Window ViewModel
 * ==========================================================================
 *
 *  PURPOSE:
 *    The ViewModel for the AmplifierSetupWindow (settings/configuration dialog).
 *    Provides a single, cohesive data interface to QML for both amplifier
 *    selection (LSL streams) and camera selection/preview. The window is
 *    shown before a recording session and collects the session configuration.
 *
 *  DESIGN PATTERN:
 *    MVVM ViewModel (QML_ELEMENT) — created per-window by QML, destroyed when
 *    the window closes. The destructor stops any active camera preview so the
 *    camera is released before the recording window takes over.
 *
 *    Facade — wraps both AmplifierManager and CameraManager behind a single
 *    class. QML only needs to know about AmplifierSetupBackend; it never
 *    binds to the two singletons directly from the setup window.
 *
 *  SESSION CONFIGURATION FLOW:
 *    1. User opens AmplifierSetupWindow (creates this ViewModel).
 *    2. User clicks "Scan" → refreshAmplifiersList() → async LSL discovery.
 *    3. User selects amplifier → channels populated via AmplifierManager.
 *    4. User selects camera → preview started via CameraManager.
 *    5. User clicks "Start" → QML collects getSelectedAmplifierId(),
 *       getSelectedCameraId(), getCurrentChannels() and passes them to
 *       EegWindow/main.qml as a JS config object → RecordingManager.
 *
 *  CAMERA PREVIEW LIFECYCLE:
 *    startCameraPreview() → CameraManager::startPreview() (hardware on)
 *    The QML VideoOutput in the settings window is connected to
 *    CameraManager::captureSession() directly (not via this class).
 *    When the window closes, ~AmplifierSetupBackend() calls stopPreview()
 *    so the camera hardware is idle before EegWindow's VideoBackend starts.
 *
 *  DATA FLOW:
 *    AmplifierManager::amplifiersListRefreshed(QList<Amplifier>)
 *      → onAmplifiersListRefreshed()    — updates m_amplifiers, notifies QML
 *    CameraManager signals (availableCamerasChanged, etc.)
 *      → re-emitted directly            — no state transformation needed
 *
 * ==========================================================================
 */

#ifndef AMPLIFIERSETUPBACKEND_H
#define AMPLIFIERSETUPBACKEND_H

#include <QObject>
#include <QProperty>
#include <QVariant>
#include <QtQml/qqmlregistration.h>
#include "amplifiermodel.h"
#include "amplifiermanager.h"
#include "cameramanager.h"

class AmplifierSetupBackend : public QObject
{
    Q_OBJECT
    QML_ELEMENT

    // --- Amplifier discovery and selection ---
    Q_PROPERTY(QVariantList availableAmplifiers READ getAvailableAmplifiers NOTIFY availableAmplifiersChanged FINAL)
    Q_PROPERTY(int selectedAmplifierIndex READ getSelectedAmplifierIndex WRITE setSelectedAmplifierIndex NOTIFY selectedAmplifierIndexChanged FINAL)
    Q_PROPERTY(QVariantList currentChannels READ getCurrentChannels NOTIFY selectedAmplifierIndexChanged FINAL)
    Q_PROPERTY(bool isLoading READ isLoading NOTIFY isLoadingChanged FINAL)

    // --- Camera selection and preview ---
    // cameraManager is CONSTANT because the singleton never changes; QML VideoOutput
    // can bind captureSession from it once and never needs to re-evaluate.
    Q_PROPERTY(CameraManager* cameraManager READ cameraManager CONSTANT FINAL)
    Q_PROPERTY(QVariantList availableCameras READ availableCameras NOTIFY availableCamerasChanged FINAL)
    Q_PROPERTY(int selectedCameraIndex READ selectedCameraIndex WRITE setSelectedCameraIndex NOTIFY selectedCameraIndexChanged FINAL)
    Q_PROPERTY(QVariantList availableFormats READ availableFormats NOTIFY availableFormatsChanged FINAL)
    Q_PROPERTY(int selectedFormatIndex READ selectedFormatIndex WRITE setSelectedFormatIndex NOTIFY selectedFormatIndexChanged FINAL)
    Q_PROPERTY(QString selectedCameraName READ selectedCameraName NOTIFY selectedCameraIndexChanged FINAL)
    Q_PROPERTY(QString selectedFormatString READ selectedFormatString NOTIFY selectedFormatIndexChanged FINAL)
    Q_PROPERTY(bool isCameraPreviewActive READ isCameraPreviewActive NOTIFY cameraPreviewActiveChanged FINAL)

public:
    explicit AmplifierSetupBackend(QObject *parent = nullptr);
    ~AmplifierSetupBackend();

    // Amplifier methods
    QVariantList getAvailableAmplifiers() const;
    int getSelectedAmplifierIndex() const;
    QVariantList getCurrentChannels() const;

    Q_INVOKABLE void refreshAmplifiersList();
    Q_INVOKABLE void setSelectedAmplifierIndex(int index);
    Q_INVOKABLE QString getSelectedAmplifierId() const;

    bool isLoading() const { return m_isLoading; }

    // Camera methods
    CameraManager* cameraManager() const { return m_cameraManager; }
    QVariantList availableCameras() const;
    int selectedCameraIndex() const;
    QVariantList availableFormats() const;
    int selectedFormatIndex() const;
    QString selectedCameraName() const;
    QString selectedFormatString() const;
    bool isCameraPreviewActive() const;

    Q_INVOKABLE void refreshCameraList();
    Q_INVOKABLE void setSelectedCameraIndex(int index);
    Q_INVOKABLE void setSelectedFormatIndex(int index);
    Q_INVOKABLE void startCameraPreview();
    Q_INVOKABLE void stopCameraPreview();
    Q_INVOKABLE QString getSelectedCameraId() const;

signals:
    // Amplifier signals
    void availableAmplifiersChanged();
    void selectedAmplifierIndexChanged();
    void currentChannelsChanged();
    void isLoadingChanged();

    // Camera signals
    void availableCamerasChanged();
    void selectedCameraIndexChanged();
    void availableFormatsChanged();
    void selectedFormatIndexChanged();
    void cameraPreviewActiveChanged();
    void cameraErrorOccurred(const QString& error);

private slots:
    void onAmplifiersListRefreshed(const QList<Amplifier>& amplifiers);
    void onCameraErrorOccurred(const QString& error);

private:
    const Amplifier* getCurrentAmplifier() const;

    AmplifierManager* m_manager;
    CameraManager* m_cameraManager;

    QList<Amplifier> m_amplifiers;
    QProperty<int> m_selectedAmplifierIndex{-1};
    bool m_isLoading = false;
};

#endif // AMPLIFIERSETUPBACKEND_H
