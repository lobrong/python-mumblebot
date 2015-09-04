import Mumble_pb2
#Global config dict, defaults go here
config = {
    "server":           "mumble.leetspeak.com.au",
    "port":             60202,
    "srcip":            "",
    "srcport":          0,
    "timeout":          10,
    "config":           "mumblebot.conf",
    "debug":            False,
    "syslog":           False,
    "username":         "mumblebot",
    "password":         "",
    "keyfile":          None,
    "certfile":         None,
    "printusers":       False,
    "printchannels":    False,
    "trigger":          "!",
    "scriptdir":        "/etc/mumblebot.d",
    "scriptwd":         "/",
    "channel":          "/",
}

#Protocol message type to class mappings.  This could be done better
#TODO: Make better.  Thanks clientkill
msgtype = (Mumble_pb2.Version,
           Mumble_pb2.UDPTunnel,
           Mumble_pb2.Authenticate,
           Mumble_pb2.Ping,
           Mumble_pb2.Reject,
           Mumble_pb2.ServerSync,
           Mumble_pb2.ChannelRemove,
           Mumble_pb2.ChannelState,
           Mumble_pb2.UserRemove,
           Mumble_pb2.UserState,
           Mumble_pb2.BanList,
           Mumble_pb2.TextMessage,
           Mumble_pb2.PermissionDenied,
           Mumble_pb2.ACL,
           Mumble_pb2.QueryUsers,
           Mumble_pb2.CryptSetup,
           Mumble_pb2.ContextActionModify,
           Mumble_pb2.ContextAction,
           Mumble_pb2.UserList,
           Mumble_pb2.VoiceTarget,
           Mumble_pb2.PermissionQuery,
           Mumble_pb2.CodecVersion,
           Mumble_pb2.UserStats,
           Mumble_pb2.RequestBlob,
           Mumble_pb2.ServerConfig,
           Mumble_pb2.SuggestConfig
)
#The other way around.  Again, could be done better
msgnum = {}
for i in range(len(msgtype)): 
    msgnum[msgtype[i].__name__] = i