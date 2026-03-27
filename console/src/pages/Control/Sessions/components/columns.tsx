import { Button, Tag, Avatar, Tooltip } from "@agentscope-ai/design";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import type { ColumnsType } from "antd/es/table";
import { UserOutlined } from "@ant-design/icons";
import { CHANNEL_COLORS, formatTime, type Session } from "./constants";

interface ColumnHandlers {
  onEdit: (session: Session) => void;
  onDelete: (sessionId: string) => void;
  t: TFunction;
}

/** Normalize ISO string to UTC for consistent sorting across mixed timezone formats. */
const toUTCTime = (ts: string | null | undefined): number => {
  if (!ts) return 0;
  const normalized =
    /[Z+\-]\d{2}:?\d{2}$/.test(ts) || ts.endsWith("Z") ? ts : ts + "Z";
  return new Date(normalized).getTime();
};

/** 获取用户名首字母或头像文字 */
const getAvatarText = (name: string): string => {
  if (!name) return "?";
  // 中文名取最后一个字，英文名取首字母
  const firstChar = name.charAt(0);
  if (/[\u4e00-\u9fa5]/.test(firstChar)) {
    // 中文名 - 取最后一个字
    return name.charAt(name.length - 1);
  }
  // 英文名 - 取首字母大写
  return firstChar.toUpperCase();
};

/** 根据用户名生成稳定的颜色 */
const getAvatarColor = (name: string): string => {
  const colors = [
    "#f56a00",
    "#7265e6",
    "#ffbf00",
    "#00a2ae",
    "#1890ff",
    "#52c41a",
    "#eb2f96",
    "#722ed1",
    "#13c2c2",
    "#fa8c16",
    "#a0d911",
    "#2f54eb",
  ];
  if (!name) return colors[0];
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
};

export const createColumns = (
  handlers: ColumnHandlers,
): ColumnsType<Session> => {
  const { t } = useTranslation();

  return [
    {
      title: "ID",
      dataIndex: "id",
      key: "id",
      width: 220,
    },
    {
      title: "发送者",
      key: "sender",
      width: 180,
      render: (_: unknown, record: Session) => {
        const senderName = (record.meta as any)?.feishu_sender_name;
        const userId = record.user_id || "";

        if (senderName) {
          const avatarText = getAvatarText(senderName);
          const avatarColor = getAvatarColor(senderName);
          return (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Avatar
                size="small"
                style={{ backgroundColor: avatarColor, flexShrink: 0 }}
              >
                {avatarText}
              </Avatar>
              <div style={{ overflow: "hidden" }}>
                <div
                  style={{
                    fontWeight: 500,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {senderName}
                </div>
                <Tooltip title={userId}>
                  <div
                    style={{
                      fontSize: "12px",
                      color: "#999",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {userId.length > 12 ? `${userId.slice(0, 12)}...` : userId}
                  </div>
                </Tooltip>
              </div>
            </div>
          );
        }

        // 没有用户名时显示用户ID
        return (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Avatar
              size="small"
              icon={<UserOutlined />}
              style={{ backgroundColor: "#ccc" }}
            />
            <Tooltip title={userId}>
              <span style={{ color: "#666" }}>
                {userId.length > 15
                  ? `${userId.slice(0, 15)}...`
                  : userId || "-"}
              </span>
            </Tooltip>
          </div>
        );
      },
    },
    {
      title: "消息",
      dataIndex: "name",
      key: "name",
      width: 150,
      ellipsis: true,
      render: (name: string) => (
        <Tooltip title={name}>
          <span style={{ color: "#666" }}>{name || "-"}</span>
        </Tooltip>
      ),
    },
    {
      title: "渠道",
      dataIndex: "channel",
      key: "channel",
      width: 100,
      render: (channel: string) => (
        <Tag color={CHANNEL_COLORS[channel] || "default"}>{channel}</Tag>
      ),
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 160,
      render: (timestamp: string | number | null) => formatTime(timestamp),
      sorter: (a: Session, b: Session) =>
        toUTCTime(a.updated_at) - toUTCTime(b.updated_at),
      defaultSortOrder: "descend",
    },
    {
      title: "操作",
      key: "action",
      width: 120,
      fixed: "right",
      render: (_: unknown, record: Session) => (
        <div style={{ display: "flex", gap: 8 }}>
          <Button
            type="link"
            size="small"
            onClick={() => handlers.onEdit(record)}
          >
            {t("common.edit")}
          </Button>
          <Button
            type="link"
            size="small"
            danger
            onClick={() => handlers.onDelete(record.id)}
          >
            {t("common.delete")}
          </Button>
        </div>
      ),
    },
  ];
};
