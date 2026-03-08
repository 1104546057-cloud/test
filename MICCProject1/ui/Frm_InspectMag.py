from PyQt5 import QtCore, QtWidgets


class Ui_Frm_InspectMag(object):
    def setupUi(self, Frm_InspectMag):
        Frm_InspectMag.setObjectName("Frm_InspectMag")
        Frm_InspectMag.resize(720, 420)

        self.centralWidget = QtWidgets.QWidget(Frm_InspectMag)
        self.centralWidget.setObjectName("centralWidget")
        Frm_InspectMag.setCentralWidget(self.centralWidget)

        self.verticalLayout = QtWidgets.QVBoxLayout(self.centralWidget)
        self.verticalLayout.setContentsMargins(16, 16, 16, 16)
        self.verticalLayout.setSpacing(12)

        self.titleLabel = QtWidgets.QLabel(self.centralWidget)
        self.titleLabel.setObjectName("titleLabel")
        self.titleLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.verticalLayout.addWidget(self.titleLabel)

        self.buttonRow = QtWidgets.QHBoxLayout()
        self.buttonRow.setSpacing(10)

        self.btn_InspectArea = QtWidgets.QPushButton(self.centralWidget)
        self.btn_InspectArea.setObjectName("btn_InspectArea")
        self.buttonRow.addWidget(self.btn_InspectArea)

        self.btn_InspectPoint = QtWidgets.QPushButton(self.centralWidget)
        self.btn_InspectPoint.setObjectName("btn_InspectPoint")
        self.buttonRow.addWidget(self.btn_InspectPoint)

        self.btn_InspectRoute = QtWidgets.QPushButton(self.centralWidget)
        self.btn_InspectRoute.setObjectName("btn_InspectRoute")
        self.buttonRow.addWidget(self.btn_InspectRoute)

        self.verticalLayout.addLayout(self.buttonRow)

        self.infoGroup = QtWidgets.QGroupBox(self.centralWidget)
        self.infoGroup.setObjectName("infoGroup")
        self.formLayout = QtWidgets.QFormLayout(self.infoGroup)
        self.formLayout.setContentsMargins(12, 12, 12, 12)

        self.txt_InspectArea = QtWidgets.QComboBox(self.infoGroup)
        self.txt_InspectArea.setObjectName("txt_InspectArea")
        self.formLayout.addRow("当前区域", self.txt_InspectArea)

        self.txt_InspectRoute = QtWidgets.QComboBox(self.infoGroup)
        self.txt_InspectRoute.setObjectName("txt_InspectRoute")
        self.formLayout.addRow("当前路线", self.txt_InspectRoute)

        self.verticalLayout.addWidget(self.infoGroup)

        self.statusLabel = QtWidgets.QLabel(self.centralWidget)
        self.statusLabel.setObjectName("statusLabel")
        self.verticalLayout.addWidget(self.statusLabel)

        self.retranslateUi(Frm_InspectMag)
        QtCore.QMetaObject.connectSlotsByName(Frm_InspectMag)

    def retranslateUi(self, Frm_InspectMag):
        _translate = QtCore.QCoreApplication.translate
        Frm_InspectMag.setWindowTitle(_translate("Frm_InspectMag", "巡检管理"))
        self.titleLabel.setText(_translate("Frm_InspectMag", "巡检总览"))
        self.btn_InspectArea.setText(_translate("Frm_InspectMag", "巡检区域"))
        self.btn_InspectPoint.setText(_translate("Frm_InspectMag", "巡检点位"))
        self.btn_InspectRoute.setText(_translate("Frm_InspectMag", "巡检路线"))
        self.infoGroup.setTitle(_translate("Frm_InspectMag", "当前数据"))
        self.statusLabel.setText(_translate("Frm_InspectMag", "请选择要进入的模块"))
